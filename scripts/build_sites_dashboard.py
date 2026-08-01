#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import json
from datetime import date
from pathlib import Path
from typing import Any

METHOD_NOTE = (
    "ChatGPTエクスポートをPC内で解析し、全件・音声除外・音声のみの送信回数など、"
    "本文を含まない数値だけを許可リスト方式で抽出しています。"
)
MONTH_KEYS = {
    "month",
    "sent_messages",
    "non_voice_messages",
    "voice_messages",
    "active_days",
    "non_voice_active_days",
    "voice_active_days",
    "conversation_count",
    "estimated_tokens",
}
DAY_KEYS = {
    "date",
    "month",
    "day",
    "sent_messages",
    "non_voice_messages",
    "voice_messages",
    "conversation_count",
    "estimated_tokens",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required private analysis output: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in private analysis output: {path.name}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"private analysis output must be an object: {path.name}")
    return payload


def as_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise SystemExit(f"invalid numeric value for {field}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"invalid numeric value for {field}") from exc
    if number < 0:
        raise SystemExit(f"negative numeric value for {field}")
    return number


def valid_month(value: Any) -> str:
    text = str(value or "")
    if len(text) != 7 or text[4] != "-" or not text[:4].isdigit() or not text[5:].isdigit():
        raise SystemExit("invalid month value in private analysis output")
    month = int(text[5:])
    if month < 1 or month > 12:
        raise SystemExit("invalid month value in private analysis output")
    return text


def valid_date(value: Any) -> str:
    text = str(value or "")
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit("invalid date value in private analysis output") from exc
    if parsed.isoformat() != text:
        raise SystemExit("invalid date value in private analysis output")
    return text


def empty_day(date_text: str) -> dict[str, Any]:
    return {
        "date": date_text,
        "month": date_text[:7],
        "day": int(date_text[8:]),
        "sent_messages": 0,
        "non_voice_messages": 0,
        "voice_messages": 0,
        "conversation_count": 0,
        "estimated_tokens": 0,
    }


def complete_daily_rows(months: list[str], rows_by_date: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for month in months:
        year = int(month[:4])
        month_number = int(month[5:])
        for day_number in range(1, calendar.monthrange(year, month_number)[1] + 1):
            date_text = f"{month}-{day_number:02d}"
            completed.append(rows_by_date.get(date_text, empty_day(date_text)))
    return completed


def validate_message_modes(row: dict[str, Any], label: str) -> None:
    if row["sent_messages"] != row["non_voice_messages"] + row["voice_messages"]:
        raise SystemExit(f"message modes do not add up for {label}")


def validate_aggregate_consistency(
    monthly_rows: list[dict[str, Any]], daily_rows: list[dict[str, Any]]
) -> None:
    for monthly in monthly_rows:
        month = monthly["month"]
        days = [row for row in daily_rows if row["month"] == month]
        checks = {
            "sent_messages": sum(row["sent_messages"] for row in days),
            "non_voice_messages": sum(row["non_voice_messages"] for row in days),
            "voice_messages": sum(row["voice_messages"] for row in days),
            "active_days": sum(1 for row in days if row["sent_messages"] > 0),
            "non_voice_active_days": sum(1 for row in days if row["non_voice_messages"] > 0),
            "voice_active_days": sum(1 for row in days if row["voice_messages"] > 0),
        }
        for field, actual in checks.items():
            if monthly[field] != actual:
                raise SystemExit(
                    f"monthly and daily {field} do not match for {month}: "
                    f"monthly={monthly[field]}, daily={actual}"
                )


def build_public_payload(summary: dict[str, Any], daily: dict[str, Any]) -> dict[str, Any]:
    summary_meta = summary.get("meta") if isinstance(summary.get("meta"), dict) else {}
    daily_meta = daily.get("meta") if isinstance(daily.get("meta"), dict) else {}
    stats = summary_meta.get("stats") if isinstance(summary_meta.get("stats"), dict) else {}

    generated_at = str(summary_meta.get("generated_at") or daily_meta.get("generated_at") or "")
    timezone = str(summary_meta.get("timezone") or daily_meta.get("timezone") or "Asia/Tokyo")
    if not generated_at:
        raise SystemExit("private analysis output does not contain generated_at")
    if timezone != "Asia/Tokyo":
        raise SystemExit("unexpected timezone in private analysis output")

    monthly_rows: list[dict[str, Any]] = []
    raw_monthly = summary.get("monthly")
    if not isinstance(raw_monthly, list) or not raw_monthly:
        raise SystemExit("private monthly summary is missing")
    seen_months: set[str] = set()
    for raw in raw_monthly:
        if not isinstance(raw, dict):
            raise SystemExit("invalid monthly row")
        month = valid_month(raw.get("month"))
        if month in seen_months:
            raise SystemExit(f"duplicate monthly row: {month}")
        seen_months.add(month)
        row = {
            "month": month,
            "sent_messages": as_non_negative_int(raw.get("user_messages", 0), "monthly user messages"),
            "non_voice_messages": as_non_negative_int(raw.get("non_voice_messages", 0), "monthly non-voice messages"),
            "voice_messages": as_non_negative_int(raw.get("voice_messages", 0), "monthly voice messages"),
            "active_days": as_non_negative_int(raw.get("active_days", 0), "monthly active days"),
            "non_voice_active_days": as_non_negative_int(raw.get("non_voice_active_days", 0), "monthly non-voice active days"),
            "voice_active_days": as_non_negative_int(raw.get("voice_active_days", 0), "monthly voice active days"),
            "conversation_count": as_non_negative_int(raw.get("conversations", 0), "monthly conversation count"),
            "estimated_tokens": as_non_negative_int(raw.get("total_tokens_est", 0), "monthly estimated tokens"),
        }
        if set(row) != MONTH_KEYS:
            raise AssertionError("monthly allowlist mismatch")
        validate_message_modes(row, month)
        monthly_rows.append(row)
    monthly_rows.sort(key=lambda row: row["month"])

    raw_daily = daily.get("daily")
    if not isinstance(raw_daily, list):
        raise SystemExit("private daily summary is missing")
    rows_by_date: dict[str, dict[str, Any]] = {}
    for raw in raw_daily:
        if not isinstance(raw, dict):
            raise SystemExit("invalid daily row")
        date_text = valid_date(raw.get("date"))
        if date_text in rows_by_date:
            raise SystemExit(f"duplicate daily row: {date_text}")
        month = valid_month(raw.get("month") or date_text[:7])
        if month != date_text[:7] or month not in seen_months:
            raise SystemExit(f"daily row references an unknown month: {date_text}")
        row = {
            "date": date_text,
            "month": month,
            "day": as_non_negative_int(raw.get("day") or int(date_text[8:]), "day"),
            "sent_messages": as_non_negative_int(raw.get("user_messages", 0), "daily user messages"),
            "non_voice_messages": as_non_negative_int(raw.get("non_voice_messages", 0), "daily non-voice messages"),
            "voice_messages": as_non_negative_int(raw.get("voice_messages", 0), "daily voice messages"),
            "conversation_count": as_non_negative_int(raw.get("conversations", 0), "daily conversation count"),
            "estimated_tokens": as_non_negative_int(raw.get("total_tokens_est", 0), "daily estimated tokens"),
        }
        if row["day"] != int(date_text[8:]):
            raise SystemExit("invalid day in private daily summary")
        if set(row) != DAY_KEYS:
            raise AssertionError("daily allowlist mismatch")
        validate_message_modes(row, date_text)
        rows_by_date[date_text] = row

    daily_rows = complete_daily_rows([row["month"] for row in monthly_rows], rows_by_date)
    validate_aggregate_consistency(monthly_rows, daily_rows)

    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "timezone": timezone,
        "method": METHOD_NOTE,
        "totals": {
            "sent_messages": sum(row["sent_messages"] for row in monthly_rows),
            "non_voice_messages": sum(row["non_voice_messages"] for row in monthly_rows),
            "voice_messages": sum(row["voice_messages"] for row in monthly_rows),
            "active_days": sum(1 for row in daily_rows if row["sent_messages"] > 0),
            "non_voice_active_days": sum(1 for row in daily_rows if row["non_voice_messages"] > 0),
            "voice_active_days": sum(1 for row in daily_rows if row["voice_messages"] > 0),
            "conversation_count": as_non_negative_int(stats.get("total_conversations", 0), "total conversation count"),
            "estimated_tokens": sum(row["estimated_tokens"] for row in monthly_rows),
        },
        "monthly": monthly_rows,
        "daily": daily_rows,
    }


def write_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the strictly allowlisted data file for the private Sites usage dashboard."
    )
    parser.add_argument("--private-output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--data-file",
        type=Path,
        default=Path("sites/usage-dashboard/public/usage-data.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    private_output_dir = args.private_output_dir.resolve()
    summary = load_json(private_output_dir / "dashboard_summary.json")
    daily = load_json(private_output_dir / "dashboard_daily.json")
    payload = build_public_payload(summary, daily)
    changed = write_if_changed(args.data_file.resolve(), payload)
    print("Sites aggregate data updated." if changed else "Sites aggregate data is unchanged.")
    print(f"Monthly rows: {len(payload['monthly'])}; daily rows: {len(payload['daily'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
