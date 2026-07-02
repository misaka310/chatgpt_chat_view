#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

# Screenshot sample only. These values are intentionally old, rounded, and synthetic.
# Do not shape this data after a real export.
MONTHLY_COUNTS = {
    "2024-01": 120,
    "2024-02": 260,
    "2024-03": 180,
    "2024-04": 440,
    "2024-05": 300,
    "2024-06": 620,
}


def month_days(year: int, month: int) -> int:
    if month == 12:
        nxt = datetime(year + 1, 1, 1, tzinfo=JST)
    else:
        nxt = datetime(year, month + 1, 1, tzinfo=JST)
    cur = datetime(year, month, 1, tzinfo=JST)
    return (nxt - cur).days


def distribute(total: int, days: int) -> list[int]:
    # Deterministic, visibly fake distribution for screenshots.
    counts = [0 for _ in range(days)]
    active_days = min(days, max(6, round(days * 0.45)))
    for i in range(active_days):
        day_index = (i * 3 + 1) % days
        counts[day_index] = max(1, total // active_days)
    diff = total - sum(counts)
    i = 0
    while diff > 0:
        day_index = (i * 5 + 2) % days
        counts[day_index] += min(7, diff)
        diff -= min(7, diff)
        i += 1
    return counts


def make_conversation(conv_id: str, title: str, start: datetime, user_count: int) -> dict:
    mapping = {}
    current = start
    node_idx = 1
    for i in range(user_count):
        message_id = f"{conv_id}-u{i + 1:04d}"
        mapping[f"n{node_idx}"] = {
            "id": f"n{node_idx}",
            "message": {
                "id": message_id,
                "author": {"role": "user"},
                "create_time": current.timestamp(),
                "content": {"parts": [f"sample user message {i + 1}"]},
            },
        }
        node_idx += 1
        current += timedelta(minutes=3 + (i % 4))
        if i % 5 == 0:
            mapping[f"n{node_idx}"] = {
                "id": f"n{node_idx}",
                "message": {
                    "id": f"{conv_id}-a{i + 1:04d}",
                    "author": {"role": "assistant"},
                    "create_time": current.timestamp(),
                    "content": {"parts": ["sample assistant response"]},
                },
            }
            node_idx += 1
            current += timedelta(minutes=1)
    return {"conversation_id": conv_id, "title": title, "mapping": mapping}


def build_export() -> list[dict]:
    conversations = []
    for month, total in MONTHLY_COUNTS.items():
        year = int(month[:4])
        month_num = int(month[5:7])
        counts = distribute(total, month_days(year, month_num))
        for day, count in enumerate(counts, start=1):
            if count <= 0:
                continue
            start = datetime(year, month_num, day, 10 + (day % 5), 0, tzinfo=JST)
            conv_id = f"fake-sample-{month}-{day:02d}"
            title = f"FAKE SAMPLE {month}-{day:02d}"
            conversations.append(make_conversation(conv_id, title, start, count))
    return conversations


def run(cmd: list[str], cwd: Path) -> None:
    print("> " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fake sample dashboard output for README screenshots.")
    parser.add_argument("--output-dir", type=Path, default=Path("sample_output"))
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--threshold", type=int, default=160)
    parser.add_argument("--window-hours", type=float, default=3.0)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output_dir).resolve()
    input_dir = output_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "conversations.json").write_text(json.dumps(build_export(), ensure_ascii=False), encoding="utf-8")

    py = sys.executable
    run([py, "analyze_chat_export.py", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--timezone", args.timezone, "--rebuild"], repo_root)
    run([py, "analyze_gpt_3h_limit.py", "--input-dir", str(input_dir), "--output-dir", str(output_dir), "--timezone", args.timezone, "--threshold", str(args.threshold), "--window-hours", str(args.window_hours)], repo_root)
    run([py, "scripts/patch_3h_html.py", "--output-dir", str(output_dir)], repo_root)
    run([py, "scripts/inject_3h_into_dashboard.py", "--output-dir", str(output_dir)], repo_root)
    run([py, "scripts/patch_dashboard_daily_chart.py", "--output-dir", str(output_dir)], repo_root)
    if (output_dir / "index.html").exists():
        (output_dir / "index.html").unlink()
    print(f"Sample dashboard: {output_dir / 'dashboard.html'}")
    print(f"Sample 3h report: {output_dir / 'gpt_3h_limit.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
