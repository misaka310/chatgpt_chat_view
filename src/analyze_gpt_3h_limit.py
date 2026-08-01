#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from analyze_chat_export import (
    build_message_dedupe_key,
    detect_inputs,
    ensure_timezone,
    extract_message_text,
    normalize_role,
    pick_timestamp,
    safe_title,
    stream_json_array,
)

DEFAULT_THRESHOLD = 160
DEFAULT_WINDOW_HOURS = 3.0


def iso_local(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def collect_user_message_events(paths: Iterable[Path], marker: Optional[str], local_tz) -> tuple[list[dict], dict]:
    events: list[dict] = []
    seen_message_keys: set[str] = set()
    total_conversation_objects = 0
    duplicate_messages_skipped = 0
    untimestamped_user_messages_skipped = 0

    for path in paths:
        file_marker = marker if path.name.lower().endswith(".html") else None
        for conversation in stream_json_array(path, marker=file_marker):
            total_conversation_objects += 1
            conv_id = (
                conversation.get("conversation_id")
                or conversation.get("id")
                or f"conv-{total_conversation_objects}"
            )
            conv_id = str(conv_id)
            title = safe_title(conversation.get("title"), f"(untitled:{conv_id[:16]})")
            mapping = conversation.get("mapping")
            if not isinstance(mapping, dict):
                continue

            for node in mapping.values():
                if not isinstance(node, dict):
                    continue
                message = node.get("message")
                if not isinstance(message, dict):
                    continue
                author = message.get("author") or {}
                role = normalize_role(author.get("role") if isinstance(author, dict) else None)
                if role != "user":
                    continue

                text = extract_message_text(message)
                msg_key = build_message_dedupe_key(conv_id, message, role, text)
                if msg_key in seen_message_keys:
                    duplicate_messages_skipped += 1
                    continue
                seen_message_keys.add(msg_key)

                ts = pick_timestamp(message)
                if ts is None:
                    untimestamped_user_messages_skipped += 1
                    continue
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz)

                message_id = message.get("id")
                if not isinstance(message_id, str) or not message_id.strip():
                    node_id = node.get("id")
                    message_id = str(node_id) if node_id else ""

                events.append(
                    {
                        "timestamp": float(ts),
                        "dt": dt,
                        "date": dt.strftime("%Y-%m-%d"),
                        "month": dt.strftime("%Y-%m"),
                        "conversation_id": conv_id,
                        "conversation_title": title,
                        "message_id": message_id,
                    }
                )

    events.sort(key=lambda row: (row["timestamp"], row["conversation_id"], row["message_id"]))
    for idx, row in enumerate(events, start=1):
        row["event_index"] = idx

    events_meta = {
        "total_conversation_objects": total_conversation_objects,
        "unique_timestamped_user_messages": len(events),
        "duplicate_user_messages_skipped": duplicate_messages_skipped,
        "untimestamped_user_messages_skipped": untimestamped_user_messages_skipped,
    }
    return events, events_meta


def empty_peak_row(key: str = "") -> dict:
    return {
        "period": key,
        "max_3h_user_messages": 0,
        "reached_threshold": False,
        "exceeded_threshold": False,
        "over_threshold_by": 0,
        "peak_window_start_jst": "",
        "peak_window_end_jst": "",
        "peak_actual_last_message_jst": "",
    }


def build_peak_row(
    period: str,
    count: int,
    start_dt: datetime,
    end_dt: datetime,
    actual_last_dt: datetime,
    threshold: int,
) -> dict:
    return {
        "period": period,
        "max_3h_user_messages": int(count),
        "reached_threshold": bool(count >= threshold),
        "exceeded_threshold": bool(count > threshold),
        "over_threshold_by": int(max(0, count - threshold)),
        "peak_window_start_jst": iso_local(start_dt),
        "peak_window_end_jst": iso_local(end_dt),
        "peak_actual_last_message_jst": iso_local(actual_last_dt),
    }


def maybe_replace_peak(current: Optional[dict], candidate: dict) -> dict:
    if current is None:
        return candidate
    if candidate["max_3h_user_messages"] > current["max_3h_user_messages"]:
        return candidate
    if candidate["max_3h_user_messages"] < current["max_3h_user_messages"]:
        return current
    if candidate.get("peak_window_start_jst", "") < current.get("peak_window_start_jst", ""):
        return candidate
    return current


def analyze_rolling_limit(events: list[dict], threshold: int, window_hours: float) -> dict:
    window_seconds = int(round(window_hours * 3600))
    window_delta = timedelta(seconds=window_seconds)
    right = 0
    overall_peak: Optional[dict] = None
    daily_peaks: dict[str, dict] = {}
    monthly_peaks: dict[str, dict] = {}
    daily_window_counts: defaultdict[str, int] = defaultdict(int)
    monthly_window_counts: defaultdict[str, int] = defaultdict(int)
    threshold_windows: list[dict] = []

    for left, start_event in enumerate(events):
        if right < left:
            right = left
        start_ts = start_event["timestamp"]
        while right < len(events) and events[right]["timestamp"] - start_ts <= window_seconds:
            right += 1

        count = right - left
        if count <= 0:
            continue

        start_dt = start_event["dt"]
        fixed_end_dt = start_dt + window_delta
        actual_last_dt = events[right - 1]["dt"]
        day = start_event["date"]
        month = start_event["month"]
        peak_candidate = build_peak_row(day, count, start_dt, fixed_end_dt, actual_last_dt, threshold)
        daily_peaks[day] = maybe_replace_peak(daily_peaks.get(day), peak_candidate)
        monthly_candidate = dict(peak_candidate)
        monthly_candidate["period"] = month
        monthly_peaks[month] = maybe_replace_peak(monthly_peaks.get(month), monthly_candidate)
        overall_candidate = dict(peak_candidate)
        overall_candidate["period"] = "all"
        overall_peak = maybe_replace_peak(overall_peak, overall_candidate)

        if count >= threshold:
            daily_window_counts[day] += 1
            monthly_window_counts[month] += 1
            threshold_windows.append(
                {
                    "window_start_jst": iso_local(start_dt),
                    "window_end_jst": iso_local(fixed_end_dt),
                    "actual_last_message_jst": iso_local(actual_last_dt),
                    "date": day,
                    "month": month,
                    "user_messages_in_3h": int(count),
                    "reached_threshold": bool(count >= threshold),
                    "exceeded_threshold": bool(count > threshold),
                    "over_threshold_by": int(max(0, count - threshold)),
                    "start_event_index": int(start_event["event_index"]),
                    "end_event_index": int(events[right - 1]["event_index"]),
                    "conversation_title_at_start": start_event.get("conversation_title", ""),
                }
            )

    daily_rows = []
    for day in sorted({row["date"] for row in events} | set(daily_peaks.keys())):
        peak = daily_peaks.get(day, empty_peak_row(day))
        row = dict(peak)
        row["date"] = day
        row.pop("period", None)
        row["threshold_window_count"] = int(daily_window_counts.get(day, 0))
        daily_rows.append(row)

    monthly_rows = []
    for month in sorted({row["month"] for row in events} | set(monthly_peaks.keys())):
        peak = monthly_peaks.get(month, empty_peak_row(month))
        row = dict(peak)
        row["month"] = month
        row.pop("period", None)
        row["threshold_window_count"] = int(monthly_window_counts.get(month, 0))
        monthly_rows.append(row)

    if overall_peak is None:
        overall_peak = empty_peak_row("all")

    threshold_windows.sort(
        key=lambda row: (
            -row["user_messages_in_3h"],
            row["window_start_jst"],
            row["start_event_index"],
        )
    )

    summary = {
        "window_hours": float(window_hours),
        "threshold_user_messages": int(threshold),
        "total_user_messages_counted": len(events),
        "max_3h_user_messages": int(overall_peak["max_3h_user_messages"]),
        "reached_threshold": bool(overall_peak["reached_threshold"]),
        "exceeded_threshold": bool(overall_peak["exceeded_threshold"]),
        "over_threshold_by": int(overall_peak["over_threshold_by"]),
        "peak_window_start_jst": overall_peak["peak_window_start_jst"],
        "peak_window_end_jst": overall_peak["peak_window_end_jst"],
        "peak_actual_last_message_jst": overall_peak["peak_actual_last_message_jst"],
        "threshold_window_count": len(threshold_windows),
        "exceeded_window_count": sum(1 for row in threshold_windows if row["exceeded_threshold"]),
    }

    return {
        "summary": summary,
        "monthly": monthly_rows,
        "daily": daily_rows,
        "threshold_windows": threshold_windows,
    }


def write_csv(path: Path, header: list[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def write_markdown_summary(path: Path, report: dict) -> None:
    summary = report["summary"]
    lines = [
        "# GPT 3h Limit Candidate Report",
        "",
        "## 結論",
        f"- 連続{summary['window_hours']:g}時間の最大送信数: {summary['max_3h_user_messages']}",
        f"- 閾値: {summary['threshold_user_messages']} user messages / {summary['window_hours']:g}h",
        f"- 閾値到達: {yes_no(summary['reached_threshold'])}",
        f"- 閾値超過: {yes_no(summary['exceeded_threshold'])}",
        f"- 超過幅: {summary['over_threshold_by']}",
        f"- ピーク窓: {summary['peak_window_start_jst']} ~ {summary['peak_window_end_jst']}",
        f"- 実際の最後の送信: {summary['peak_actual_last_message_jst']}",
        "",
        "## 注意",
        "- これはChatGPTエクスポート内の `author.role == user` を数えたローカル集計です。",
        "- モデル別の公式利用量ではありません。GPT-5.5以外の送信、Thinking、添付、ツール利用も混ざる可能性があります。",
        "- そのため、公式制限の確定判定ではなく、160/3hに達した可能性を見るための候補レポートです。",
        "",
        "## 出力",
        "- `gpt_3h_limit.html`",
        "- `gpt_3h_limit_summary.json`",
        "- `gpt_3h_limit_monthly.csv`",
        "- `gpt_3h_limit_daily.csv`",
        "- `gpt_3h_limit_windows.csv`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def build_html_report(report: dict) -> str:
    summary = report["summary"]
    daily_rows = report.get("daily", [])
    monthly_rows = report.get("monthly", [])
    windows = report.get("threshold_windows", [])[:50]
    status_text = "超過あり" if summary["exceeded_threshold"] else "超過なし"
    reached_text = "到達あり" if summary["reached_threshold"] else "到達なし"
    card_rows = [
        ("連続3時間の最大送信数", summary["max_3h_user_messages"], "user messages"),
        ("閾値", summary["threshold_user_messages"], f"/ {summary['window_hours']:g}h"),
        ("判定", status_text, reached_text),
        ("ピーク窓", summary["peak_window_start_jst"], f"〜 {summary['peak_window_end_jst']}"),
    ]
    cards_html = "\n".join(
        f'<div class="card"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div><div class="unit">{esc(unit)}</div></div>'
        for label, value, unit in card_rows
    )
    monthly_html = "\n".join(
        f"<tr><td>{esc(row.get('month'))}</td><td class='num'>{esc(row.get('max_3h_user_messages'))}</td><td>{esc(row.get('reached_threshold'))}</td><td>{esc(row.get('exceeded_threshold'))}</td><td>{esc(row.get('peak_window_start_jst'))}</td></tr>"
        for row in monthly_rows
    ) or "<tr><td colspan='5'>データなし</td></tr>"
    top_daily = sorted(daily_rows, key=lambda r: (-int(r.get("max_3h_user_messages", 0)), str(r.get("date", ""))))[:30]
    daily_html = "\n".join(
        f"<tr><td>{esc(row.get('date'))}</td><td class='num'>{esc(row.get('max_3h_user_messages'))}</td><td>{esc(row.get('reached_threshold'))}</td><td>{esc(row.get('exceeded_threshold'))}</td><td>{esc(row.get('peak_window_start_jst'))}</td></tr>"
        for row in top_daily
    ) or "<tr><td colspan='5'>データなし</td></tr>"
    windows_html = "\n".join(
        f"<tr><td>{esc(row.get('window_start_jst'))}</td><td>{esc(row.get('window_end_jst'))}</td><td class='num'>{esc(row.get('user_messages_in_3h'))}</td><td>{esc(row.get('exceeded_threshold'))}</td><td>{esc(row.get('conversation_title_at_start'))}</td></tr>"
        for row in windows
    ) or "<tr><td colspan='5'>160到達ウィンドウなし</td></tr>"
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GPT 3時間160送信チェック</title>
  <style>
    body {{ margin: 0; background: #f4f7fb; color: #1d2733; font-family: "Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif; line-height: 1.5; }}
    .wrap {{ max-width: 1160px; margin: 0 auto; padding: 20px 16px 40px; display: grid; gap: 16px; }}
    .panel {{ background: #fff; border: 1px solid #d8e0ea; border-radius: 14px; padding: 16px; box-shadow: 0 4px 18px rgba(25,45,65,0.06); }}
    h1, h2 {{ margin: 0 0 8px; }}
    h1 {{ font-size: 1.45rem; }}
    h2 {{ font-size: 1.08rem; }}
    .sub, .unit, .label {{ color: #5d6b7c; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }}
    .card {{ border: 1px solid #d8e0ea; border-radius: 12px; padding: 12px; background: linear-gradient(180deg, #fff, #f9fcff); }}
    .value {{ margin-top: 4px; font-size: 1.25rem; font-weight: 700; }}
    .notice {{ border-left: 4px solid #f2b07d; background: #fff2e8; padding: 8px 10px; border-radius: 8px; color: #7c4a21; font-size: 0.9rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ border-bottom: 1px solid #d8e0ea; padding: 7px 8px; text-align: left; vertical-align: top; }}
    th {{ color: #5d6b7c; font-weight: 700; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .ok {{ display: inline-block; border-radius: 999px; background: #e9f7ef; color: #166534; padding: 3px 10px; font-weight: 700; }}
    .bad {{ display: inline-block; border-radius: 999px; background: #fde8e8; color: #8b1d1d; padding: 3px 10px; font-weight: 700; }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>GPT 3時間160送信チェック</h1>
      <div class="sub">ChatGPTエクスポートから、任意の連続3時間で160送信に到達・超過した候補を確認します。</div>
      <p>{'<span class="bad">超過あり</span>' if summary['exceeded_threshold'] else '<span class="ok">超過なし</span>'}</p>
    </section>
    <section class="panel"><div class="cards">{cards_html}</div></section>
    <section class="panel">
      <h2>注意</h2>
      <div class="notice">これは公式のモデル別利用量ではありません。ChatGPTエクスポート上のユーザー送信を数えるため、GPT-5.5以外、Thinking、添付、ツール利用などが混ざる可能性があります。</div>
      <p><a href="dashboard.html">Return to dashboard / ダッシュボードへ戻る</a></p>
    </section>
    <section class="panel">
      <h2>月別ピーク</h2>
      <table><thead><tr><th>月</th><th>最大3時間送信数</th><th>160到達</th><th>160超過</th><th>ピーク開始</th></tr></thead><tbody>{monthly_html}</tbody></table>
    </section>
    <section class="panel">
      <h2>日別ピーク 上位30件</h2>
      <table><thead><tr><th>日付</th><th>最大3時間送信数</th><th>160到達</th><th>160超過</th><th>ピーク開始</th></tr></thead><tbody>{daily_html}</tbody></table>
    </section>
    <section class="panel">
      <h2>160到達ウィンドウ 上位50件</h2>
      <table><thead><tr><th>開始</th><th>終了</th><th>送信数</th><th>160超過</th><th>開始時の会話</th></tr></thead><tbody>{windows_html}</tbody></table>
    </section>
  </div>
</body>
</html>
"""


def write_html_report(path: Path, report: dict) -> None:
    path.write_text(build_html_report(report), encoding="utf-8")


def build_report(input_dir: Path, timezone_name: str, threshold: int, window_hours: float) -> dict:
    paths, marker = detect_inputs(input_dir)
    local_tz = ensure_timezone(timezone_name)
    events, events_meta = collect_user_message_events(paths, marker, local_tz)
    rolling = analyze_rolling_limit(events, threshold=threshold, window_hours=window_hours)
    return {
        "meta": {
            "generated_at": datetime.now().astimezone().isoformat(),
            "timezone": getattr(local_tz, "key", str(local_tz)),
            "input_files": [str(p) for p in paths],
            "definitions": {
                "counted_messages": "ChatGPT export messages where author.role == user and a timestamp is available",
                "window": "any continuous local-time window starting at a counted user message",
                "reached_threshold": "max_3h_user_messages >= threshold_user_messages",
                "exceeded_threshold": "max_3h_user_messages > threshold_user_messages",
                "official_usage_warning": "This is not model-specific official ChatGPT usage. It is a local candidate count from the export.",
            },
            "stats": events_meta,
        },
        **rolling,
    }


def write_outputs(output_dir: Path, report: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "gpt_3h_limit_summary.json", report)
    write_markdown_summary(output_dir / "gpt_3h_limit_summary.md", report)
    write_html_report(output_dir / "gpt_3h_limit.html", report)
    write_csv(
        output_dir / "gpt_3h_limit_monthly.csv",
        [
            "month",
            "max_3h_user_messages",
            "reached_threshold",
            "exceeded_threshold",
            "over_threshold_by",
            "peak_window_start_jst",
            "peak_window_end_jst",
            "peak_actual_last_message_jst",
            "threshold_window_count",
        ],
        report["monthly"],
    )
    write_csv(
        output_dir / "gpt_3h_limit_daily.csv",
        [
            "date",
            "max_3h_user_messages",
            "reached_threshold",
            "exceeded_threshold",
            "over_threshold_by",
            "peak_window_start_jst",
            "peak_window_end_jst",
            "peak_actual_last_message_jst",
            "threshold_window_count",
        ],
        report["daily"],
    )
    write_csv(
        output_dir / "gpt_3h_limit_windows.csv",
        [
            "window_start_jst",
            "window_end_jst",
            "actual_last_message_jst",
            "date",
            "month",
            "user_messages_in_3h",
            "reached_threshold",
            "exceeded_threshold",
            "over_threshold_by",
            "start_event_index",
            "end_event_index",
            "conversation_title_at_start",
        ],
        report["threshold_windows"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count candidate ChatGPT 3-hour usage limit windows from an export."
    )
    parser.add_argument("--input-dir", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_HOURS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.threshold <= 0:
        raise SystemExit("--threshold must be positive")
    if args.window_hours <= 0:
        raise SystemExit("--window-hours must be positive")

    report = build_report(args.input_dir, args.timezone, args.threshold, args.window_hours)
    write_outputs(args.output_dir, report)
    summary = report["summary"]
    print(
        "max_3h_user_messages="
        f"{summary['max_3h_user_messages']} "
        f"threshold={summary['threshold_user_messages']} "
        f"exceeded={summary['exceeded_threshold']} "
        "html=gpt_3h_limit.html"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
