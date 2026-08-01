#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from contextlib import contextmanager
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "sites" / "usage-dashboard"
PUBLIC_DIR = SITE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "usage-data.json"
DIST_DIR = SITE_DIR / "dist"
BUILD_STATE_FILE = SITE_DIR / ".sites-build-state.json"
INSTALL_STATE_FILE = SITE_DIR / ".npm-install-state.json"
INSTALL_LOCK_DIR = SITE_DIR / ".npm-install.lock"
NPM_CACHE_DIR = SITE_DIR / ".npm-cache"
PRIVATE_OUTPUT_DIR = REPO_ROOT / "output"
PREVIEW_HOST = "127.0.0.1"
PREVIEW_PORT = 8734
MIN_NODE_VERSION = (22, 13, 0)

EXCLUDED_DIRS = {
    ".git",
    ".next",
    ".npm-cache",
    ".npm-install.lock",
    ".npm-stage",
    ".vinext",
    ".wrangler",
    "=",
    "dist",
    "node_modules",
    "outputs",
    "work",
}


def subprocess_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.lower() == "npm_config_cache":
            env.pop(key)
    NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env["npm_config_cache"] = str(NPM_CACHE_DIR)
    if os.name == "nt":
        env.setdefault("SystemRoot", r"C:\Windows")
        env.setdefault("ComSpec", str(Path(env["SystemRoot"]) / "System32" / "cmd.exe"))
    return env


def run(
    command: list[str],
    cwd: Path = REPO_ROOT,
    *,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("> " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def node_command() -> str:
    command = shutil.which("node")
    if not command:
        raise SystemExit("Node.js 22.13 or later is required for the Sites dashboard.")
    return command


def parse_node_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", text.strip())
    if not match:
        raise SystemExit(f"Could not read the Node.js version: {text.strip() or '(empty)'}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def checked_node_version(node: str, env: dict[str, str]) -> str:
    completed = run([node, "--version"], SITE_DIR, env=env, capture_output=True)
    value = completed.stdout.strip()
    if parse_node_version(value) < MIN_NODE_VERSION:
        minimum = ".".join(str(part) for part in MIN_NODE_VERSION)
        raise SystemExit(f"Node.js {minimum} or later is required; found {value}.")
    return value


def npm_cli(node: str) -> Path:
    path = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if not path.is_file():
        raise SystemExit("npm could not be found next to Node.js.")
    return path


def digest_files(paths: list[Path], labels: list[str]) -> str:
    digest = hashlib.sha256()
    for path, label in zip(paths, labels, strict=True):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def install_fingerprint(node_version: str) -> str:
    paths = [SITE_DIR / "package.json", SITE_DIR / "package-lock.json"]
    return digest_files(paths, [path.name for path in paths]) + ":" + node_version


def load_state(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def save_state(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def dependency_files_complete(root: Path) -> bool:
    required = (
        root / "vinext" / "dist" / "cli.js",
        root / "unrs-resolver" / "package.json",
        root / "@unrs" / "resolver-binding-win32-x64-msvc" / "package.json",
        root / "@rolldown" / "binding-win32-x64-msvc" / "package.json",
    )
    return all(path.is_file() for path in required)


def dependency_tree_works(node: str, root: Path, env: dict[str, str]) -> bool:
    if not dependency_files_complete(root):
        return False
    completed = subprocess.run(
        [node, "-e", "require('unrs-resolver');"],
        cwd=root.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def install_lock():
    owner_path = INSTALL_LOCK_DIR / "owner.json"
    try:
        INSTALL_LOCK_DIR.mkdir()
    except FileExistsError:
        owner = load_state(owner_path) or {}
        owner_pid = int(owner.get("pid", 0) or 0)
        if process_is_running(owner_pid):
            raise SystemExit(
                f"Another Sites dependency setup is already running (PID {owner_pid})."
            )
        shutil.rmtree(INSTALL_LOCK_DIR, ignore_errors=True)
        INSTALL_LOCK_DIR.mkdir()
    owner_path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": time.time()}, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        yield
    finally:
        shutil.rmtree(INSTALL_LOCK_DIR, ignore_errors=True)


def install_staged_dependencies(
    node: str, npm_path: Path, env: dict[str, str]
) -> Path:
    stage_dir = SITE_DIR / f".npm-stage-{os.getpid()}-{time.time_ns()}"
    stage_dir.mkdir()
    shutil.copy2(SITE_DIR / "package.json", stage_dir / "package.json")
    shutil.copy2(SITE_DIR / "package-lock.json", stage_dir / "package-lock.json")
    try:
        run(
            [
                node,
                str(npm_path),
                "ci",
                "--ignore-scripts",
                "--prefer-online",
                "--no-audit",
                "--no-fund",
            ],
            stage_dir,
            env=env,
        )
        staged_modules = stage_dir / "node_modules"
        if not dependency_tree_works(node, staged_modules, env):
            raise SystemExit("The staged Sites dependency tree failed its integrity check.")

        current_modules = SITE_DIR / "node_modules"
        backup_modules = SITE_DIR / f".node_modules-old-{os.getpid()}-{time.time_ns()}"
        if current_modules.exists():
            current_modules.replace(backup_modules)
        try:
            staged_modules.replace(current_modules)
        except Exception:
            if backup_modules.exists() and not current_modules.exists():
                backup_modules.replace(current_modules)
            raise
        shutil.rmtree(backup_modules, ignore_errors=True)
        return current_modules
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def dependencies_are_current(
    fingerprint: str, node: str, env: dict[str, str]
) -> bool:
    modules = SITE_DIR / "node_modules"
    return (
        load_state(INSTALL_STATE_FILE)
        == {"version": 1, "fingerprint": fingerprint}
        and dependency_tree_works(node, modules, env)
    )


def ensure_dependencies(node: str, npm_path: Path, node_version: str, env: dict[str, str]) -> Path:
    fingerprint = install_fingerprint(node_version)
    if not dependencies_are_current(fingerprint, node, env):
        with install_lock():
            if not dependencies_are_current(fingerprint, node, env):
                install_staged_dependencies(node, npm_path, env)
                save_state(INSTALL_STATE_FILE, {"version": 1, "fingerprint": fingerprint})
    vinext_cli = SITE_DIR / "node_modules" / "vinext" / "dist" / "cli.js"
    if not vinext_cli.is_file():
        raise SystemExit("The verified Sites dependency environment is incomplete.")
    return vinext_cli


def fingerprint_site() -> str:
    digest = hashlib.sha256()
    for path in sorted(SITE_DIR.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(SITE_DIR).parts
        if any(
            part in EXCLUDED_DIRS
            or part.startswith(".npm-stage-")
            or part.startswith(".node_modules-old-")
            for part in relative_parts
        ):
            continue
        if path in {BUILD_STATE_FILE, INSTALL_STATE_FILE}:
            continue
        relative = path.relative_to(SITE_DIR).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_is_current(fingerprint: str) -> bool:
    return (DIST_DIR / "server" / "index.js").is_file() and load_state(BUILD_STATE_FILE) == {
        "version": 1,
        "fingerprint": fingerprint,
    }


def wait_for_preview(process: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit("Sites preview server stopped before it became ready.")
        try:
            with socket.create_connection((PREVIEW_HOST, PREVIEW_PORT), timeout=0.4):
                return
        except OSError:
            time.sleep(0.25)
    process.terminate()
    raise SystemExit("Sites preview server did not become ready.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze locally, build the safe Sites dashboard, verify it, and preview it.")
    parser.add_argument("--force-analysis", action="store_true")
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--skip-analysis", action="store_true", help="Reuse analysis prepared by start.bat.")
    parser.add_argument("--no-open", action="store_true", help="Build and verify without starting the browser preview.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python = sys.executable

    if not args.skip_analysis:
        analysis_command = [python, str(REPO_ROOT / "scripts" / "start_dashboard.py"), "--no-open"]
        if args.force_analysis:
            analysis_command.append("--force")
        run(analysis_command)

    run(
        [
            python,
            str(REPO_ROOT / "scripts" / "build_sites_dashboard.py"),
            "--private-output-dir",
            str(PRIVATE_OUTPUT_DIR),
            "--data-file",
            str(DATA_FILE),
        ]
    )
    run(
        [
            python,
            str(REPO_ROOT / "scripts" / "verify_sites_public.py"),
            "--public-source",
            str(PUBLIC_DIR),
            "--private-output-dir",
            str(PRIVATE_OUTPUT_DIR),
        ]
    )

    env = subprocess_environment()
    node = node_command()
    node_version = checked_node_version(node, env)
    npm_path = npm_cli(node)
    vinext_cli = ensure_dependencies(node, npm_path, node_version, env)

    fingerprint = fingerprint_site()
    if not args.force_build and build_is_current(fingerprint):
        print("Sites source and aggregate data are unchanged. Reusing the existing build.")
    else:
        run([node, str(vinext_cli), "build"], SITE_DIR, env=env)
        save_state(BUILD_STATE_FILE, {"version": 1, "fingerprint": fingerprint})

    run(
        [
            python,
            str(REPO_ROOT / "scripts" / "verify_sites_public.py"),
            "--public-source",
            str(PUBLIC_DIR),
            "--artifact-root",
            str(DIST_DIR),
            "--private-output-dir",
            str(PRIVATE_OUTPUT_DIR),
        ]
    )

    if args.no_open:
        print("Sites dashboard build and verification complete.")
        return 0

    url = f"http://{PREVIEW_HOST}:{PREVIEW_PORT}/"
    command = [node, str(vinext_cli), "dev", "--host", PREVIEW_HOST, "--port", str(PREVIEW_PORT)]
    print("> " + " ".join(command), flush=True)
    process = subprocess.Popen(command, cwd=SITE_DIR, env=env)
    try:
        wait_for_preview(process)
        print(f"Opening safe Sites preview: {url}")
        webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
