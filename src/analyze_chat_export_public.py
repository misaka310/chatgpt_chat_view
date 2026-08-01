#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from chat_export_core import (
    build_message_dedupe_key,
    detect_inputs,
    ensure_timezone,
    extract_message_text,
    is_voice_message,
    normalize_role,
    pick_timestamp,
    safe_title,
    stream_json_array,
)


def fallback_token_estimate(text: str) -> int:
    stripped = (text or "").strip()
    if not stripped:
        return 0
    ascii_chars = sum(1 for ch in stripped if ord(ch) < 128)
    non_ascii_chars = len(stripped) - ascii_chars
    return max(1, int(round((ascii_chars / 4.0) + non_ascii_chars)))


def build_token_estimator():
    try:
        import tiktoken  # type: ignore
        enc = tiktoken.get_encoding("o200k_base")
        return lambda text: len(enc.encode((text or "").strip(), disallowed_special=())) if (text or "").strip() else 0, "tiktoken:o200k_base"
    except Exception:
        return fallback_token_estimate, "char_fallback_v1"


def median_value(values: list[int]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return float(values[mid])
    return float((values[mid - 1] + values[mid]) / 2.0)


def month_days(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def iso_from_timestamp(ts: Optional[float], tz_obj) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz_obj).isoformat()


def choose_title(current: str, candidate: str) -> str:
    if not current:
        return candidate
    if current.startswith("(untitled:") and not candidate.startswith("(untitled:"):
        return candidate
    return current if len(current) >= len(candidate) else candidate


def collect_stats(paths: Iterable[Path], marker: Optional[str], local_tz) -> dict:
    estimate_tokens, token_method = build_token_estimator()
    monthly_user: Counter[str] = Counter()
    monthly_voice_user: Counter[str] = Counter()
    monthly_non_voice_user: Counter[str] = Counter()
    monthly_conv_ids: dict[str, set[str]] = defaultdict(set)
    monthly_active_days: dict[str, set[str]] = defaultdict(set)
    monthly_voice_active_days: dict[str, set[str]] = defaultdict(set)
    monthly_non_voice_active_days: dict[str, set[str]] = defaultdict(set)
    monthly_daily_user_counts: dict[str, Counter[int]] = defaultdict(Counter)
    monthly_role_counts: dict[str, Counter[str]] = defaultdict(Counter)
    monthly_role_tokens: dict[str, Counter[str]] = defaultdict(Counter)
    daily_user: Counter[str] = Counter()
    daily_voice_user: Counter[str] = Counter()
    daily_non_voice_user: Counter[str] = Counter()
    daily_conv_ids: dict[str, set[str]] = defaultdict(set)
    daily_tokens: Counter[str] = Counter()
    daily_hourly: Counter[tuple[str, int]] = Counter()
    daily_hourly_voice: Counter[tuple[str, int]] = Counter()
    daily_hourly_non_voice: Counter[tuple[str, int]] = Counter()
    daily_conv_user_counts: dict[str, Counter[str]] = defaultdict(Counter)
    conversation_stats: dict[str, dict] = {}
    conv_titles: dict[str, str] = {}
    seen_keys: set[str] = set()
    total_conversation_objects = 0
    duplicate_messages = 0
    unique_messages = 0
    timestamped_messages = 0

    for path in paths:
        file_marker = marker if path.name.lower().endswith(".html") else None
        for conversation in stream_json_array(path, marker=file_marker):
            total_conversation_objects += 1
            conv_id = str(conversation.get("conversation_id") or conversation.get("id") or f"conv-{total_conversation_objects}")
            title = safe_title(conversation.get("title"), f"(untitled:{conv_id[:16]})")
            conv_titles[conv_id] = choose_title(conv_titles.get(conv_id, ""), title)
            stats = conversation_stats.setdefault(
                conv_id,
                {
                    "conversation_id": conv_id,
                    "title": conv_titles[conv_id],
                    "first_ts": None,
                    "last_ts": None,
                    "user": 0,
                    "voice_user": 0,
                    "non_voice_user": 0,
                    "assistant": 0,
                    "total": 0,
                    "active_days": set(),
                },
            )
            stats["title"] = conv_titles[conv_id]
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
                text = extract_message_text(message)
                voice_user = role == "user" and is_voice_message(message)
                key = build_message_dedupe_key(conv_id, message, role, text)
                if key in seen_keys:
                    duplicate_messages += 1
                    continue
                seen_keys.add(key)
                unique_messages += 1
                stats["total"] += 1
                if role == "user":
                    stats["user"] += 1
                    if voice_user:
                        stats["voice_user"] += 1
                    else:
                        stats["non_voice_user"] += 1
                elif role == "assistant":
                    stats["assistant"] += 1
                ts = pick_timestamp(message)
                if ts is None:
                    continue
                timestamped_messages += 1
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz)
                month = dt.strftime("%Y-%m")
                day = dt.strftime("%Y-%m-%d")
                hour = dt.hour
                token_est = int(estimate_tokens(text))
                stats["first_ts"] = ts if stats["first_ts"] is None else min(stats["first_ts"], ts)
                stats["last_ts"] = ts if stats["last_ts"] is None else max(stats["last_ts"], ts)
                stats["active_days"].add(day)
                monthly_role_counts[month][role] += 1
                monthly_role_tokens[month][role] += token_est
                daily_tokens[day] += token_est
                if role == "user":
                    monthly_user[month] += 1
                    monthly_conv_ids[month].add(conv_id)
                    monthly_active_days[month].add(day)
                    monthly_daily_user_counts[month][dt.day] += 1
                    daily_user[day] += 1
                    daily_conv_ids[day].add(conv_id)
                    daily_hourly[(day, hour)] += 1
                    if voice_user:
                        monthly_voice_user[month] += 1
                        monthly_voice_active_days[month].add(day)
                        daily_voice_user[day] += 1
                        daily_hourly_voice[(day, hour)] += 1
                    else:
                        monthly_non_voice_user[month] += 1
                        monthly_non_voice_active_days[month].add(day)
                        daily_non_voice_user[day] += 1
                        daily_hourly_non_voice[(day, hour)] += 1
                    daily_conv_user_counts[day][conv_id] += 1

    months = sorted(set(monthly_user) | set(monthly_conv_ids) | set(monthly_role_counts))
    latest_month = max(months) if months else None
    monthly_rows = []
    role_monthly_rows = []
    for month in months:
        role_counts = monthly_role_counts.get(month, Counter())
        role_tokens = monthly_role_tokens.get(month, Counter())
        user_count = int(monthly_user.get(month, 0))
        active_days = len(monthly_active_days.get(month, set()))
        voice_count = int(monthly_voice_user[month])
        non_voice_count = int(monthly_non_voice_user[month])
        voice_days = len(monthly_voice_active_days[month])
        non_voice_days = len(monthly_non_voice_active_days[month])
        total_days = month_days(month)
        last_data_day = max(monthly_daily_user_counts.get(month, Counter()).keys(), default=0)
        elapsed_days = last_data_day if month == latest_month and 0 < last_data_day < total_days else total_days
        elapsed_days = max(1, elapsed_days)
        daily_series = [int(monthly_daily_user_counts.get(month, Counter()).get(day, 0)) for day in range(1, elapsed_days + 1)]
        day_counter = monthly_daily_user_counts.get(month, Counter())
        if day_counter:
            peak_day, peak_count = min(day_counter.items(), key=lambda kv: (-kv[1], kv[0]))
            peak_date = f"{month}-{peak_day:02d}"
        else:
            peak_count = 0
            peak_date = ""
        user_tokens = int(role_tokens.get("user", 0))
        total_tokens = int(sum(role_tokens.values()))
        monthly_rows.append({
            "month": month,
            "year": month[:4],
            "user_messages": user_count,
            "non_voice_messages": non_voice_count,
            "voice_messages": voice_count,
            "assistant_messages": int(role_counts.get("assistant", 0)),
            "system_messages": int(role_counts.get("system", 0)),
            "tool_messages": int(role_counts.get("tool", 0)),
            "other_messages": int(role_counts.get("other", 0)),
            "total_messages": int(sum(role_counts.values())),
            "conversations": int(len(monthly_conv_ids.get(month, set()))),
            "active_days": int(active_days),
            "user_tokens_est": user_tokens,
            "non_voice_active_days": int(non_voice_days),
            "voice_active_days": int(voice_days),
            "avg_non_voice_per_active_day": float(non_voice_count / non_voice_days) if non_voice_days else 0.0,
            "avg_voice_per_active_day": float(voice_count / voice_days) if voice_days else 0.0,
            "assistant_tokens_est": int(role_tokens.get("assistant", 0)),
            "system_tokens_est": int(role_tokens.get("system", 0)),
            "tool_tokens_est": int(role_tokens.get("tool", 0)),
            "other_tokens_est": int(role_tokens.get("other", 0)),
            "total_tokens_est": total_tokens,
            "avg_user_tokens_est": float(user_tokens / user_count) if user_count else 0.0,
            "avg_tokens_per_active_day_est": float(total_tokens / active_days) if active_days else 0.0,
            "avg_per_elapsed_day": float(user_count / elapsed_days),
            "avg_per_active_day": float(user_count / active_days) if active_days else 0.0,
            "median_daily_user_messages": median_value(daily_series),
            "peak_daily_user_messages": int(peak_count),
            "peak_daily_date": peak_date,
        })
        role_monthly_rows.append({"month": month, "year": month[:4], "user": int(role_counts.get("user", 0)), "assistant": int(role_counts.get("assistant", 0)), "system": int(role_counts.get("system", 0)), "tool": int(role_counts.get("tool", 0)), "other": int(role_counts.get("other", 0)), "total": int(sum(role_counts.values()))})

    days = sorted(daily_user.keys())
    daily_rows = [{"date": day, "year": day[:4], "month": day[:7], "day": int(day[8:10]), "weekday": datetime.strptime(day, "%Y-%m-%d").weekday(), "user_messages": int(daily_user[day]), "conversations": int(len(daily_conv_ids.get(day, set()))), "total_tokens_est": int(daily_tokens.get(day, 0))} for day in days]
    daily_hourly_rows = [{"date": day, "hour": hour, "user_messages": int(daily_hourly.get((day, hour), 0))} for day in days for hour in range(24)]
    for row in daily_rows:
        day = row["date"]
        row["non_voice_messages"] = int(daily_non_voice_user[day])
        row["voice_messages"] = int(daily_voice_user[day])
    for row in daily_hourly_rows:
        key = (row["date"], row["hour"])
        row["non_voice_messages"] = int(daily_hourly_non_voice[key])
        row["voice_messages"] = int(daily_hourly_voice[key])
    daily_top_rows = []
    for day in days:
        for rank, (conv_id, count) in enumerate(daily_conv_user_counts.get(day, Counter()).most_common(20), start=1):
            daily_top_rows.append({"date": day, "rank": rank, "conversation_id": conv_id, "title": conv_titles.get(conv_id, ""), "user_messages": int(count)})

    conversation_index = []
    for conv_id, stats in conversation_stats.items():
        conversation_index.append({"conversation_id": conv_id, "title": conv_titles.get(conv_id, stats["title"]), "first_message_at": iso_from_timestamp(stats["first_ts"], local_tz), "last_message_at": iso_from_timestamp(stats["last_ts"], local_tz), "user_message_count": int(stats["user"]), "assistant_message_count": int(stats["assistant"]), "total_message_count": int(stats["total"]), "active_days": len(stats["active_days"]), "inferred_category": "", "top_keywords": []})

    for row in conversation_index:
        stats = conversation_stats[row["conversation_id"]]
        row["non_voice_message_count"] = int(stats["non_voice_user"])
        row["voice_message_count"] = int(stats["voice_user"])
    return {
        "meta": {"stats": {"total_conversation_objects": total_conversation_objects, "total_unique_messages": unique_messages, "total_duplicate_messages_skipped": duplicate_messages, "total_conversations": len(conversation_stats), "total_timestamped_messages": timestamped_messages, "token_estimation_method": token_method}},
        "monthly": monthly_rows,
        "daily": daily_rows,
        "daily_hourly": daily_hourly_rows,
        "monthly_weekday_hour": [],
        "daily_top_conversations": daily_top_rows,
        "role_monthly": role_monthly_rows,
        "conversation_index": sorted(conversation_index, key=lambda r: r.get("last_message_at") or "", reverse=True),
        "category_monthly": [],
        "category_daily": [],
        "keywords_monthly": [],
    }


def write_csv(path: Path, headers: list[str], rows: Iterable[Iterable[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_outputs(output_dir: Path, parsed: dict) -> None:
    monthly = sorted(parsed.get("monthly", []), key=lambda r: r["month"])
    daily = sorted(parsed.get("daily", []), key=lambda r: r["date"])
    write_json(output_dir / "parsed_summary.json", parsed)
    write_json(output_dir / "dashboard_summary.json", {"meta": parsed.get("meta", {}), "monthly": monthly})
    write_json(output_dir / "dashboard_daily.json", {"meta": parsed.get("meta", {}), "daily": daily, "daily_hourly": parsed.get("daily_hourly", []), "monthly_weekday_hour": [], "daily_top_conversations": parsed.get("daily_top_conversations", [])})
    write_json(output_dir / "dashboard_conversations.json", {"meta": parsed.get("meta", {}), "total": len(parsed.get("conversation_index", [])), "items": parsed.get("conversation_index", [])})
    write_json(output_dir / "dashboard_categories.json", {"meta": parsed.get("meta", {}), "category_monthly": [], "category_daily": [], "keywords_monthly": [], "role_monthly": parsed.get("role_monthly", [])})
    write_csv(output_dir / "monthly_user_messages.csv", ["month", "user_messages"], [[r["month"], r["user_messages"]] for r in monthly])
    write_csv(output_dir / "monthly_user_messages_by_mode.csv", ["month", "all_messages", "non_voice_messages", "voice_messages"], [[r["month"], r["user_messages"], r.get("non_voice_messages", 0), r.get("voice_messages", 0)] for r in monthly])
    write_csv(output_dir / "monthly_conversations.csv", ["month", "conversations"], [[r["month"], r["conversations"]] for r in monthly])
    write_csv(output_dir / "monthly_active_days.csv", ["month", "active_days"], [[r["month"], r["active_days"]] for r in monthly])
    write_csv(output_dir / "daily_user_messages.csv", ["date", "user_messages"], [[r["date"], r["user_messages"]] for r in daily])
    write_csv(output_dir / "daily_hourly_user_messages.csv", ["date", "hour", "user_messages"], [[r["date"], r["hour"], r["user_messages"]] for r in parsed.get("daily_hourly", [])])
    write_csv(output_dir / "daily_user_messages_by_mode.csv", ["date", "all_messages", "non_voice_messages", "voice_messages"], [[r["date"], r["user_messages"], r.get("non_voice_messages", 0), r.get("voice_messages", 0)] for r in daily])
    write_csv(output_dir / "daily_hourly_user_messages_by_mode.csv", ["date", "hour", "all_messages", "non_voice_messages", "voice_messages"], [[r["date"], r["hour"], r["user_messages"], r.get("non_voice_messages", 0), r.get("voice_messages", 0)] for r in parsed.get("daily_hourly", [])])
    write_csv(output_dir / "daily_conversations.csv", ["date", "conversations"], [[r["date"], r["conversations"]] for r in daily])
    write_csv(output_dir / "conversations_index.csv", ["conversation_id", "title", "first_message_at", "last_message_at", "user_message_count", "assistant_message_count", "total_message_count", "active_days", "inferred_category", "top_keywords"], [[r.get("conversation_id", ""), r.get("title", ""), r.get("first_message_at", ""), r.get("last_message_at", ""), r.get("user_message_count", 0), r.get("assistant_message_count", 0), r.get("total_message_count", 0), r.get("active_days", 0), r.get("inferred_category", ""), ""] for r in parsed.get("conversation_index", [])])
    write_csv(output_dir / "category_monthly.csv", ["month", "category", "total_message_count", "user_message_count", "assistant_message_count", "conversation_count"], [])
    write_csv(output_dir / "category_daily.csv", ["date", "category", "total_message_count", "user_message_count", "assistant_message_count", "conversation_count"], [])
    write_csv(output_dir / "keywords_monthly.csv", ["month", "keyword", "count"], [])
    (output_dir / "monthly_summary.md").write_text("# Monthly User Messages\n\n" + "\n".join([f"- {r['month']}: {r['user_messages']}" for r in monthly]) + "\n", encoding="utf-8")
    template_path = Path(__file__).with_name("dashboard.template.html")
    (output_dir / "dashboard.html").write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze ChatGPT export and generate static dashboard outputs.")
    parser.add_argument("--input-dir", default="input")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--timezone", default="Asia/Tokyo")
    parser.add_argument("--rules", default="rules/category_keywords.json")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files, marker = detect_inputs(input_dir)
    local_tz = ensure_timezone(args.timezone)
    parsed = collect_stats(input_files, marker, local_tz)
    parsed.setdefault("meta", {})
    parsed["meta"]["timezone"] = args.timezone
    parsed["meta"]["input_files"] = [str(p) for p in input_files]
    parsed["meta"]["generated_at"] = datetime.now().astimezone().isoformat()
    write_outputs(output_dir, parsed)
    print("Mode: parsed raw export")
    print("Input files:")
    for path in input_files:
        print(f"  - {path}")
    print("Output files:")
    for name in ("dashboard.html", "dashboard_summary.json", "dashboard_daily.json", "monthly_user_messages.csv", "daily_user_messages.csv", "parsed_summary.json"):
        print(f"  - {output_dir / name}")


if __name__ == "__main__":
    main()
