#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SRC_DIR = REPO_ROOT / "src"
ASSETS_DIR = REPO_ROOT / "assets"
INPUT_DIR = REPO_ROOT / "input"
OUTPUT_DIR = REPO_ROOT / "output"
STATE_PATH = OUTPUT_DIR / ".analysis-state.json"
REQUIRED_OUTPUTS = (
    "dashboard.html",
    "dashboard_summary.json",
    "dashboard_daily.json",
    "gpt_3h_limit.html",
    "gpt_3h_limit_summary.json",
)
PIPELINE_FILES = (
    SRC_DIR / "analyze_chat_export.py",
    SRC_DIR / "analyze_chat_export_public.py",
    SRC_DIR / "analyze_gpt_3h_limit.py",
    SRC_DIR / "chat_export_core.py",
    SRC_DIR / "dashboard.template.html",
    ASSETS_DIR / "favicon.svg",
    REPO_ROOT / "scripts" / "patch_3h_html.py",
    REPO_ROOT / "scripts" / "inject_3h_into_dashboard.py",
    REPO_ROOT / "scripts" / "patch_dashboard_daily_chart.py",
)

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SRC_DIR))

from chat_export_core import detect_inputs  # noqa: E402
from open_dashboard import serve  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_files(paths: Iterable[Path], base: Path) -> list[dict[str, object]]:
    result = []
    for path in sorted(paths, key=lambda item: str(item).lower()):
        stat = path.stat()
        try:
            name = str(path.relative_to(base))
        except ValueError:
            name = str(path)
        result.append(
            {
                "name": name.replace("\\", "/"),
                "size": stat.st_size,
                "sha256": sha256_file(path),
            }
        )
    return result


def pipeline_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in PIPELINE_FILES:
        digest.update(str(path.relative_to(REPO_ROOT)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_state(input_files: Iterable[Path]) -> dict[str, object]:
    return {
        "version": 1,
        "timezone": "Asia/Tokyo",
        "threshold": 160,
        "window_hours": 3,
        "pipeline_sha256": pipeline_fingerprint(),
        "inputs": fingerprint_files(input_files, INPUT_DIR),
    }


def load_state(path: Path | None = None) -> dict[str, object] | None:
    state_path = path or STATE_PATH
    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def outputs_are_complete(output_dir: Path | None = None) -> bool:
    target = output_dir or OUTPUT_DIR
    return all((target / name).is_file() for name in REQUIRED_OUTPUTS)


def analysis_is_current(expected_state: dict[str, object]) -> bool:
    return outputs_are_complete() and load_state() == expected_state


def run_checked(command: list[str]) -> None:
    print("> " + " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def analyze() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    run_checked(
        [
            python,
            str(SRC_DIR / "analyze_chat_export.py"),
            "--input-dir",
            str(INPUT_DIR),
            "--output-dir",
            str(OUTPUT_DIR),
            "--timezone",
            "Asia/Tokyo",
            "--rebuild",
        ]
    )
    run_checked(
        [
            python,
            str(SRC_DIR / "analyze_gpt_3h_limit.py"),
            "--input-dir",
            str(INPUT_DIR),
            "--output-dir",
            str(OUTPUT_DIR),
            "--timezone",
            "Asia/Tokyo",
            "--threshold",
            "160",
            "--window-hours",
            "3",
        ]
    )
    for script in (
        "patch_3h_html.py",
        "inject_3h_into_dashboard.py",
        "patch_dashboard_daily_chart.py",
    ):
        run_checked([python, str(REPO_ROOT / "scripts" / script), "--output-dir", str(OUTPUT_DIR)])
    shutil.copy2(ASSETS_DIR / "favicon.svg", OUTPUT_DIR / "favicon.svg")
    for legacy_name in ("index.html", "dashboard_codex_match.json"):
        legacy_path = OUTPUT_DIR / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()


def save_state(state: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze changed input and open the local dashboard.")
    parser.add_argument("--force", action="store_true", help="Analyze even when the input is unchanged.")
    parser.add_argument("--no-open", action="store_true", help="Analyze only; do not start the browser server.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_files, _ = detect_inputs(INPUT_DIR)
    expected_state = build_state(input_files)

    if not args.force and analysis_is_current(expected_state):
        print("Input is unchanged. Reusing the existing analysis.")
    else:
        print("Input changed or no complete analysis exists. Running analysis...")
        STATE_PATH.unlink(missing_ok=True)
        analyze()
        save_state(expected_state)
        print("Analysis complete.")

    if not args.no_open:
        serve(OUTPUT_DIR, 8733, "dashboard.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
