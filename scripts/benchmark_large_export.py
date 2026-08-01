#!/usr/bin/env python3
"""Generate a deterministic fake export and measure the local analysis pipeline."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from analyze_chat_export_public import collect_stats, write_outputs as write_dashboard_outputs
from analyze_gpt_3h_limit import build_report, write_outputs as write_limit_outputs
from chat_export_core import ensure_timezone


def write_synthetic_export(path: Path, messages: int, per_conversation: int) -> int:
    """Write without retaining the generated export in memory; all values are fake."""
    base_timestamp = 1_704_067_200  # 2024-01-01T00:00:00Z, deliberately fixed
    conversations = 0
    with path.open("w", encoding="utf-8") as f:
        f.write("[")
        for offset in range(0, messages, per_conversation):
            if conversations:
                f.write(",")
            count = min(per_conversation, messages - offset)
            mapping = {
                f"n{index:05d}": {
                    "id": f"n{index:05d}",
                    "message": {
                        "id": f"synthetic-{offset + index:08d}",
                        "author": {"role": "user"},
                        # 90 seconds avoids intentionally manufacturing 3h-limit hits.
                        "create_time": base_timestamp + (offset + index) * 90,
                        "content": {"parts": [f"Synthetic benchmark message {offset + index}"]},
                    },
                }
                for index in range(count)
            }
            json.dump(
                {
                    "conversation_id": f"synthetic-benchmark-{conversations:05d}",
                    "title": f"Synthetic benchmark conversation {conversations:05d}",
                    "mapping": mapping,
                },
                f,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            conversations += 1
        f.write("]")
    return conversations


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def run_benchmark(messages: int, per_conversation: int, timezone_name: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="chatgpt-export-benchmark-") as temp_name:
        temp = Path(temp_name)
        input_dir = temp / "input"
        output_dir = temp / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        export_path = input_dir / "conversations.json"
        conversation_count = write_synthetic_export(export_path, messages, per_conversation)

        tz = ensure_timezone(timezone_name)
        tracemalloc.start()
        started = time.perf_counter()
        try:
            parsed = collect_stats([export_path], None, tz)
            write_dashboard_outputs(output_dir, parsed)
            report = build_report(input_dir, timezone_name, threshold=160, window_hours=3.0)
            write_limit_outputs(output_dir, report)
            success = True
            error = ""
        except Exception as exc:  # keep a machine-readable failure record for benchmark runs
            success = False
            error = f"{type(exc).__name__}: {exc}"
        elapsed_seconds = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        return {
            "success": success,
            "error": error,
            "input_file_bytes": export_path.stat().st_size,
            "conversations": conversation_count,
            "messages": messages,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "python_tracemalloc_peak_bytes": peak_bytes,
            "output_bytes": directory_size(output_dir) if output_dir.exists() else 0,
            "token_estimation_method": parsed["meta"]["stats"]["token_estimation_method"] if success else "",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark deterministic synthetic ChatGPT exports.")
    parser.add_argument("--messages", type=int, required=True, help="Number of synthetic messages to generate.")
    parser.add_argument("--per-conversation", type=int, default=1_000)
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--report-file", type=Path, help="Optional JSON result file outside the temporary data directory.")
    args = parser.parse_args()
    if args.messages <= 0 or args.per_conversation <= 0:
        raise SystemExit("--messages and --per-conversation must be positive")
    result = run_benchmark(args.messages, args.per_conversation, args.timezone)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.report_file:
        args.report_file.parent.mkdir(parents=True, exist_ok=True)
        args.report_file.write_text(text + "\n", encoding="utf-8")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
