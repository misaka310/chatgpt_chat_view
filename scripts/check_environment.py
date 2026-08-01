#!/usr/bin/env python3
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_exact_requirements(path: Path) -> list[tuple[str, str]]:
    requirements: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            raise ValueError(f"{path}:{line_number}: only exact name==version requirements are supported")
        name, expected = (part.strip() for part in line.split("==", 1))
        if not name or not expected:
            raise ValueError(f"{path}:{line_number}: invalid requirement {raw_line!r}")
        requirements.append((name, expected))
    return requirements


def environment_mismatches(
    requirements_path: Path,
    get_version: Callable[[str], str] = version,
) -> list[str]:
    mismatches: list[str] = []
    for name, expected in parse_exact_requirements(requirements_path):
        try:
            actual = get_version(name)
        except PackageNotFoundError:
            mismatches.append(f"{name}: missing (expected {expected})")
            continue
        if actual != expected:
            mismatches.append(f"{name}: installed {actual}, expected {expected}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the virtual environment against pinned requirements.")
    parser.add_argument("--requirements", type=Path, default=REPO_ROOT / "requirements.txt")
    args = parser.parse_args()

    try:
        mismatches = environment_mismatches(args.requirements.resolve())
    except (OSError, ValueError) as exc:
        print(exc)
        return 1

    if mismatches:
        for mismatch in mismatches:
            print(mismatch)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
