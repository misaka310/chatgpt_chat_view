#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore


CHUNK_SIZE = 1024 * 1024
CHAT_HTML_MARKER = "var jsonData ="
PARSED_REQUIRED_KEYS = (
    "meta",
    "monthly",
    "daily",
    "daily_hourly",
    "monthly_weekday_hour",
    "daily_top_conversations",
    "role_monthly",
    "conversation_index",
)
DEFAULT_CATEGORY_RULES_PATH = Path("rules/category_keywords.json")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+#./-]{2,}|[ぁ-んァ-ヶー一-龠]{2,}")


def stream_json_array(path: Path, marker: Optional[str] = None) -> Iterator[dict]:
    decoder = json.JSONDecoder()
    marker_found = marker is None
    array_started = False
    eof = False
    buf = ""
    pos = 0
    with path.open("r", encoding="utf-8") as f:
        while True:
            if pos >= len(buf):
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    if not array_started:
                        raise ValueError(f"JSON array start not found in {path}")
                    return
                buf = chunk
                pos = 0
            if marker and not marker_found:
                while True:
                    idx = buf.find(marker, pos)
                    if idx >= 0:
                        pos = idx + len(marker)
                        marker_found = True
                        break
                    keep = buf[-(len(marker) - 1) :] if len(marker) > 1 else ""
                    chunk = f.read(CHUNK_SIZE)
                    if chunk == "":
                        raise ValueError(f"Marker '{marker}' not found in {path}")
                    buf = keep + chunk
                    pos = 0
            if not array_started:
                while True:
                    while pos < len(buf) and buf[pos] != "[":
                        pos += 1
                    if pos < len(buf):
                        pos += 1
                        array_started = True
                        break
                    chunk = f.read(CHUNK_SIZE)
                    if chunk == "":
                        raise ValueError(f"JSON array start '[' not found in {path}")
                    buf = chunk
                    pos = 0
            while True:
                while pos < len(buf) and (buf[pos].isspace() or buf[pos] == ","):
                    pos += 1
                if pos < len(buf):
                    break
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    eof = True
                    break
                buf = buf[pos:] + chunk
                pos = 0
            if eof:
                return
            if buf[pos] == "]":
                return
            try:
                item, end = decoder.raw_decode(buf, pos)
                pos = end
                if isinstance(item, dict):
                    yield item
            except json.JSONDecodeError:
                chunk = f.read(CHUNK_SIZE)
                if chunk == "":
                    raise
                buf = buf[pos:] + chunk
                pos = 0


def detect_inputs(base_dir: Path) -> tuple[list[Path], Optional[str]]:
    shards = sorted(base_dir.glob("conversations-*.json"))
    if shards:
        return shards, None
    single = base_dir / "conversations.json"
    if single.exists():
        return [single], None
    html = base_dir / "chat.html"
    if html.exists():
        return [html], CHAT_HTML_MARKER
    raise FileNotFoundError(
        "No input file found. Put conversations-*.json, conversations.json, or chat.html in the input directory."
    )


def ensure_timezone(tz_name: Optional[str]):
    if tz_name:
        if ZoneInfo is not None:
            try:
                return ZoneInfo(tz_name)
            except Exception:
                pass
        fallback = {"UTC": 0, "Etc/UTC": 0, "Asia/Tokyo": 9}
        if tz_name in fallback:
            return timezone(timedelta(hours=fallback[tz_name]), name=tz_name)
        raise RuntimeError(f"Timezone '{tz_name}' could not be resolved.")
    local_tz = datetime.now().astimezone().tzinfo
    return local_tz or timezone.utc


def pick_timestamp(message: dict) -> Optional[float]:
    for key in ("create_time", "update_time"):
        value = message.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def normalize_role(role: Optional[str]) -> str:
    if not role:
        return "other"
    value = role.strip().lower()
    if value in ("user", "assistant", "system", "tool"):
        return value
    return "other"


def has_required_parsed_shape(parsed: Any) -> bool:
    return isinstance(parsed, dict) and all(k in parsed for k in PARSED_REQUIRED_KEYS)


def should_reuse_parsed(parsed_path: Path, inputs: list[Path], rules_path: Path) -> bool:
    if not parsed_path.exists():
        return False
    parsed_mtime = parsed_path.stat().st_mtime
    deps = list(inputs)
    if rules_path.exists():
        deps.append(rules_path)
    return all(p.stat().st_mtime <= parsed_mtime for p in deps)


def safe_title(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def choose_title(current: str, candidate: str) -> str:
    if not current:
        return candidate
    current_is_fallback = current.startswith("(untitled:")
    candidate_is_fallback = candidate.startswith("(untitled:")
    if current_is_fallback and not candidate_is_fallback:
        return candidate
    if not current_is_fallback and candidate_is_fallback:
        return current
    return current if len(current) >= len(candidate) else candidate


def extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            text_parts = [
                str(part).strip()
                for part in parts
                if isinstance(part, (str, int, float)) and str(part).strip()
            ]
            if text_parts:
                return "\n".join(text_parts)
        text_value = content.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()
    if isinstance(content, list):
        text_parts = [
            str(part).strip()
            for part in content
            if isinstance(part, (str, int, float)) and str(part).strip()
        ]
        if text_parts:
            return "\n".join(text_parts)
    return ""


def extract_message_text(message: dict) -> str:
    content = message.get("content")
    return extract_text_from_content(content)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def tokenize_text(value: str, stopwords: set[str]) -> list[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    tokens = []
    for token in TOKEN_PATTERN.findall(normalized):
        if token in stopwords:
            continue
        if len(token) < 2:
            continue
        tokens.append(token)
    return tokens


def build_message_dedupe_key(conv_id: str, message: dict, role: str, text: str) -> str:
    message_id = message.get("id")
    if isinstance(message_id, str) and message_id.strip():
        return f"{conv_id}::id::{message_id.strip()}"

    timestamp = pick_timestamp(message)
    ts_part = "none" if timestamp is None else f"{timestamp:.6f}"
    fallback_payload = {
        "role": role,
        "timestamp": ts_part,
        "text": normalize_text(text)[:1200],
        "recipient": normalize_text(str(message.get("recipient") or ""))[:120],
    }
    digest = hashlib.sha1(
        json.dumps(fallback_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"{conv_id}::fallback::{digest}"


def load_category_rules(path: Path) -> dict:
    rules = json.loads(path.read_text(encoding="utf-8"))
    categories = rules.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError(f"Invalid category rules at {path}: categories is required")

    normalized_categories = []
    for item in categories:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        keywords = item.get("keywords")
        if not isinstance(name, str) or not name.strip() or not isinstance(keywords, list):
            continue
        normalized_categories.append(
            {
                "name": name.strip(),
                "keywords": [normalize_text(str(k)) for k in keywords if str(k).strip()],
            }
        )

    if not normalized_categories:
        raise ValueError(f"Invalid category rules at {path}: no usable category definitions")

    stopwords = {
        normalize_text(str(x))
        for x in rules.get("keyword_stopwords", [])
        if isinstance(x, (str, int, float)) and normalize_text(str(x))
    }

    fallback_category = rules.get("fallback_category")
    if not isinstance(fallback_category, str) or not fallback_category.strip():
        fallback_category = "その他"

    return {
        "categories": normalized_categories,
        "stopwords": stopwords,
        "fallback_category": fallback_category.strip(),
        "top_keywords_limit": int(rules.get("top_keywords_limit", 8)),
        "keywords_monthly_limit": int(rules.get("keywords_monthly_limit", 100)),
        "daily_top_conversations_limit": int(rules.get("daily_top_conversations_limit", 20)),
    }


def add_category_scores(counter: Counter[str], text: str, rules: dict) -> None:
    normalized = normalize_text(text)
    if not normalized:
        return
    for category in rules["categories"]:
        score = 0
        for keyword in category["keywords"]:
            if keyword and keyword in normalized:
                score += 1
        if score:
            counter[category["name"]] += score


def infer_category(scores: Counter[str], rules: dict) -> str:
    if not scores:
        return rules["fallback_category"]
    best_score = max(scores.values())
    if best_score <= 0:
        return rules["fallback_category"]
    ordered_names = [category["name"] for category in rules["categories"]]
    for name in ordered_names:
        if scores.get(name, 0) == best_score:
            return name
    return rules["fallback_category"]


def iso_from_timestamp(ts: Optional[float], tz_obj) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz_obj).isoformat()


def collect_stats_from_inputs(paths: Iterable[Path], marker: Optional[str], local_tz, rules: dict) -> dict:
    monthly_user: Counter[str] = Counter()
    monthly_conv_ids: Dict[str, set[str]] = defaultdict(set)
    monthly_active_days: Dict[str, set[str]] = defaultdict(set)
    daily_user: Counter[str] = Counter()
    daily_conv_ids: Dict[str, set[str]] = defaultdict(set)
    daily_hourly: Counter[tuple[str, int]] = Counter()
    monthly_weekday_hour: Counter[tuple[str, int, int]] = Counter()
    daily_conv_user_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    monthly_role_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    conv_titles: Dict[str, str] = {}
    conversation_stats: Dict[str, dict] = {}
    monthly_keyword_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    seen_message_keys: set[str] = set()

    total_conversation_objects = 0
    total_unique_messages = 0
    total_duplicate_messages_skipped = 0
    total_timestamped_messages = 0

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
            fallback_title = f"(untitled:{conv_id[:16]})"
            title = safe_title(conversation.get("title"), fallback_title)

            previous_title = conv_titles.get(conv_id, "")
            conv_titles[conv_id] = choose_title(previous_title, title)

            stats = conversation_stats.get(conv_id)
            if stats is None:
                stats = {
                    "conversation_id": conv_id,
                    "title": conv_titles[conv_id],
                    "first_ts": None,
                    "last_ts": None,
                    "user": 0,
                    "assistant": 0,
                    "total": 0,
                    "active_days": set(),
                    "keyword_counts": Counter(),
                    "category_scores": Counter(),
                    "monthly_roles": defaultdict(Counter),
                    "daily_roles": defaultdict(Counter),
                    "title_scored": False,
                }
                conversation_stats[conv_id] = stats
            else:
                stats["title"] = conv_titles[conv_id]

            if not stats["title_scored"]:
                add_category_scores(stats["category_scores"], stats["title"], rules)
                stats["keyword_counts"].update(tokenize_text(stats["title"], rules["stopwords"]))
                stats["title_scored"] = True

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
                msg_key = build_message_dedupe_key(conv_id, message, role, text)
                if msg_key in seen_message_keys:
                    total_duplicate_messages_skipped += 1
                    continue
                seen_message_keys.add(msg_key)
                total_unique_messages += 1

                stats["total"] += 1
                if role == "user":
                    stats["user"] += 1
                elif role == "assistant":
                    stats["assistant"] += 1

                add_category_scores(stats["category_scores"], text, rules)
                tokens = tokenize_text(text, rules["stopwords"])
                if tokens:
                    stats["keyword_counts"].update(tokens)

                ts = pick_timestamp(message)
                if ts is None:
                    continue

                total_timestamped_messages += 1
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz)
                month = dt.strftime("%Y-%m")
                day = dt.strftime("%Y-%m-%d")
                hour = dt.hour
                weekday = dt.weekday()

                first_ts = stats["first_ts"]
                last_ts = stats["last_ts"]
                stats["first_ts"] = ts if first_ts is None else min(first_ts, ts)
                stats["last_ts"] = ts if last_ts is None else max(last_ts, ts)
                stats["active_days"].add(day)
                stats["monthly_roles"][month][role] += 1
                stats["daily_roles"][day][role] += 1

                monthly_role_counts[month][role] += 1
                if role == "user":
                    monthly_user[month] += 1
                    monthly_conv_ids[month].add(conv_id)
                    monthly_active_days[month].add(day)
                    daily_user[day] += 1
                    daily_conv_ids[day].add(conv_id)
                    daily_hourly[(day, hour)] += 1
                    monthly_weekday_hour[(month, weekday, hour)] += 1
                    daily_conv_user_counts[day][conv_id] += 1

                if tokens:
                    monthly_keyword_counts[month].update(tokens)

    months = sorted(
        set(monthly_user.keys())
        | set(monthly_conv_ids.keys())
        | set(monthly_active_days.keys())
        | set(monthly_role_counts.keys())
    )

    monthly_rows = []
    role_monthly_rows = []
    for month in months:
        role_counts = monthly_role_counts.get(month, Counter())
        monthly_rows.append(
            {
                "month": month,
                "year": month[:4],
                "user_messages": int(monthly_user.get(month, 0)),
                "conversations": int(len(monthly_conv_ids.get(month, set()))),
                "active_days": int(len(monthly_active_days.get(month, set()))),
            }
        )
        role_monthly_rows.append(
            {
                "month": month,
                "year": month[:4],
                "user": int(role_counts.get("user", 0)),
                "assistant": int(role_counts.get("assistant", 0)),
                "system": int(role_counts.get("system", 0)),
                "tool": int(role_counts.get("tool", 0)),
                "other": int(role_counts.get("other", 0)),
                "total": int(sum(role_counts.values())),
            }
        )

    days = sorted(daily_user.keys())
    daily_rows = [
        {
            "date": day,
            "year": day[:4],
            "month": day[:7],
            "day": int(day[8:10]),
            "weekday": datetime.strptime(day, "%Y-%m-%d").weekday(),
            "user_messages": int(daily_user[day]),
            "conversations": int(len(daily_conv_ids.get(day, set()))),
        }
        for day in days
    ]
    daily_hourly_rows = [
        {"date": day, "hour": hour, "user_messages": int(daily_hourly.get((day, hour), 0))}
        for day in days
        for hour in range(24)
    ]
    monthly_weekday_hour_rows = [
        {
            "month": month,
            "weekday": weekday,
            "hour": hour,
            "user_messages": int(monthly_weekday_hour.get((month, weekday, hour), 0)),
        }
        for month in months
        for weekday in range(7)
        for hour in range(24)
    ]

    conversation_index = []
    category_monthly_acc: Dict[tuple[str, str], dict] = {}
    category_daily_acc: Dict[tuple[str, str], dict] = {}

    for conv_id, stats in conversation_stats.items():
        category = infer_category(stats["category_scores"], rules)
        keywords = [
            token
            for token, _ in stats["keyword_counts"].most_common(max(1, rules["top_keywords_limit"]))
        ]

        conversation_index.append(
            {
                "conversation_id": conv_id,
                "title": conv_titles.get(conv_id, stats["title"]),
                "first_message_at": iso_from_timestamp(stats["first_ts"], local_tz),
                "last_message_at": iso_from_timestamp(stats["last_ts"], local_tz),
                "user_message_count": int(stats["user"]),
                "assistant_message_count": int(stats["assistant"]),
                "total_message_count": int(stats["total"]),
                "active_days": int(len(stats["active_days"])),
                "inferred_category": category,
                "top_keywords": keywords,
            }
        )

        for month, roles in stats["monthly_roles"].items():
            key = (month, category)
            current = category_monthly_acc.setdefault(
                key,
                {
                    "month": month,
                    "category": category,
                    "total_message_count": 0,
                    "user_message_count": 0,
                    "assistant_message_count": 0,
                    "conversation_ids": set(),
                },
            )
            current["total_message_count"] += int(sum(roles.values()))
            current["user_message_count"] += int(roles.get("user", 0))
            current["assistant_message_count"] += int(roles.get("assistant", 0))
            current["conversation_ids"].add(conv_id)

        for day, roles in stats["daily_roles"].items():
            key = (day, category)
            current = category_daily_acc.setdefault(
                key,
                {
                    "date": day,
                    "category": category,
                    "total_message_count": 0,
                    "user_message_count": 0,
                    "assistant_message_count": 0,
                    "conversation_ids": set(),
                },
            )
            current["total_message_count"] += int(sum(roles.values()))
            current["user_message_count"] += int(roles.get("user", 0))
            current["assistant_message_count"] += int(roles.get("assistant", 0))
            current["conversation_ids"].add(conv_id)

    conversation_index.sort(
        key=lambda row: (
            row["last_message_at"] or "",
            row["total_message_count"],
            row["conversation_id"],
        ),
        reverse=True,
    )

    daily_top_conversations_rows = []
    conversation_index_lookup = {row["conversation_id"]: row for row in conversation_index}
    for day in days:
        ordered = sorted(
            daily_conv_user_counts.get(day, Counter()).items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        for rank, (conv_id, count) in enumerate(
            ordered[: max(1, rules["daily_top_conversations_limit"])], start=1
        ):
            index_row = conversation_index_lookup.get(conv_id, {})
            daily_top_conversations_rows.append(
                {
                    "date": day,
                    "rank": rank,
                    "conversation_id": conv_id,
                    "title": conv_titles.get(conv_id, f"(untitled:{conv_id[:16]})"),
                    "user_messages": int(count),
                    "total_message_count": int(index_row.get("total_message_count", 0)),
                    "inferred_category": index_row.get(
                        "inferred_category", rules["fallback_category"]
                    ),
                }
            )

    category_monthly_rows = []
    for row in category_monthly_acc.values():
        category_monthly_rows.append(
            {
                "month": row["month"],
                "category": row["category"],
                "total_message_count": int(row["total_message_count"]),
                "user_message_count": int(row["user_message_count"]),
                "assistant_message_count": int(row["assistant_message_count"]),
                "conversation_count": int(len(row["conversation_ids"])),
            }
        )
    category_monthly_rows.sort(key=lambda r: (r["month"], r["category"]))

    category_daily_rows = []
    for row in category_daily_acc.values():
        category_daily_rows.append(
            {
                "date": row["date"],
                "category": row["category"],
                "total_message_count": int(row["total_message_count"]),
                "user_message_count": int(row["user_message_count"]),
                "assistant_message_count": int(row["assistant_message_count"]),
                "conversation_count": int(len(row["conversation_ids"])),
            }
        )
    category_daily_rows.sort(key=lambda r: (r["date"], r["category"]))

    keywords_monthly_rows = []
    for month in sorted(monthly_keyword_counts.keys()):
        for keyword, count in monthly_keyword_counts[month].most_common(
            max(1, rules["keywords_monthly_limit"])
        ):
            keywords_monthly_rows.append(
                {
                    "month": month,
                    "keyword": keyword,
                    "count": int(count),
                }
            )

    return {
        "meta": {
            "generated_at": datetime.now().astimezone().isoformat(),
            "timezone": getattr(local_tz, "key", str(local_tz)),
            "input_files": [str(p) for p in paths],
            "rules_file": str(rules.get("rules_path", "")),
            "definitions": {
                "user_messages": "author.role == user",
                "conversation_count": "unique conversation_id with >=1 user message in period",
                "active_days": "unique local dates with >=1 user message in period",
                "timestamp_priority": "create_time first, then update_time",
                "message_dedupe": "conversation_id + message.id. If message.id is unavailable, conversation_id + fallback hash(role,timestamp,text,recipient).",
            },
            "stats": {
                "total_conversation_objects": total_conversation_objects,
                "total_unique_messages": total_unique_messages,
                "total_duplicate_messages_skipped": total_duplicate_messages_skipped,
                "total_timestamped_messages": total_timestamped_messages,
                "total_conversations": len(conversation_index),
            },
        },
        "monthly": monthly_rows,
        "daily": daily_rows,
        "daily_hourly": daily_hourly_rows,
        "monthly_weekday_hour": monthly_weekday_hour_rows,
        "daily_top_conversations": daily_top_conversations_rows,
        "role_monthly": role_monthly_rows,
        "conversation_index": conversation_index,
        "category_monthly": category_monthly_rows,
        "category_daily": category_daily_rows,
        "keywords_monthly": keywords_monthly_rows,
    }


def write_csv(path: Path, header: list[str], rows: Iterable[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_monthly_summary_md(path: Path, parsed: dict) -> None:
    monthly = sorted(parsed["monthly"], key=lambda r: r["month"])
    lines = [
        "# Monthly Usage Summary",
        "",
        "## 集計ルール",
        "- user_messages: `author.role == user`",
        "- conversations: 期間内に user メッセージが1件以上ある conversation_id のユニーク数",
        "- active_days: 期間内に user メッセージが1件以上あるローカル日付のユニーク数",
        "- timestamp: `create_time` 優先、なければ `update_time`",
        "",
        "## 月次",
    ]
    if not monthly:
        lines.append("- データなし")
    else:
        for row in monthly:
            lines.append(
                f"- `{row['month']}`: user={row['user_messages']} / conversations={row['conversations']} / active_days={row['active_days']}"
            )
    lines.extend(
        [
            "",
            "## 生成情報",
            f"- timezone: `{parsed['meta'].get('timezone', 'unknown')}`",
            f"- generated_at: `{parsed['meta'].get('generated_at', 'unknown')}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _json_for_html(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_dashboard_html(parsed: dict) -> str:
    payload = _json_for_html(parsed)
    template = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChatGPT Export Dashboard</title>
  <style>
    :root {
      --bg: #f4f6f9;
      --card: #ffffff;
      --line: #d7dde6;
      --ink: #1f2937;
      --muted: #5b6678;
      --accent: #2f6feb;
      --accent-soft: #e8f0ff;
      --warn: #b7551f;
      --radius: 12px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif;
      background:
        radial-gradient(900px 300px at -10% 0%, #dce8ff 0%, transparent 55%),
        radial-gradient(700px 240px at 120% -10%, #ffe6d7 0%, transparent 60%),
        var(--bg);
    }
    .wrap {
      max-width: 1500px;
      margin: 0 auto;
      padding: 18px;
      display: grid;
      gap: 14px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: 0 4px 16px rgba(10, 20, 40, 0.06);
      padding: 14px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      align-items: end;
    }
    h1 { margin: 0; font-size: 1.35rem; }
    h2 { margin: 0 0 8px; font-size: 1.05rem; }
    p { margin: 6px 0 0; color: var(--muted); }
    .meta { color: var(--muted); font-size: 0.9rem; display: flex; gap: 14px; flex-wrap: wrap; }
    .kpis {
      display: grid;
      grid-template-columns: repeat(5, minmax(150px, 1fr));
      gap: 10px;
    }
    .kpi {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      background: linear-gradient(180deg, #ffffff, #f9fbff);
    }
    .kpi-label { color: var(--muted); font-size: 0.82rem; }
    .kpi-value { margin-top: 6px; font-size: 1.24rem; font-weight: 700; }
    .grid2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(4, minmax(190px, 1fr));
      gap: 10px;
      align-items: end;
    }
    label { display: block; font-size: 0.83rem; color: var(--muted); margin-bottom: 4px; }
    input, select {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font-size: 0.92rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      font-size: 0.87rem;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #f6f9ff;
      color: var(--muted);
      z-index: 1;
    }
    .table-wrap {
      border: 1px solid var(--line);
      border-radius: 10px;
      max-height: 460px;
      overflow: auto;
    }
    .small-table-wrap {
      border: 1px solid var(--line);
      border-radius: 10px;
      max-height: 300px;
      overflow: auto;
    }
    .mono { font-family: Consolas, "Courier New", monospace; }
    .chip {
      display: inline-block;
      background: var(--accent-soft);
      color: #204a9a;
      border: 1px solid #c8dafd;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.76rem;
      white-space: nowrap;
    }
    .link-btn {
      border: 0;
      background: transparent;
      color: var(--accent);
      cursor: pointer;
      padding: 0;
      text-decoration: underline;
      text-align: left;
      font-size: 0.86rem;
    }
    .muted { color: var(--muted); }
    .row-highlight td { background: #fff4e9; }
    .bar-line {
      height: 8px;
      border-radius: 999px;
      background: #ecf2ff;
      overflow: hidden;
    }
    .bar-line > span {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #4a83f0, #77a6ff);
    }
    .empty { color: var(--muted); font-size: 0.9rem; }
    @media (max-width: 1200px) {
      .kpis { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
      .controls { grid-template-columns: 1fr 1fr; }
      .grid2 { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card header">
      <div>
        <h1>ChatGPT エクスポート分析ダッシュボード</h1>
        <p>ローカルファイル専用表示。タイムゾーン: <span id="tz"></span></p>
      </div>
      <div class="meta" id="topMeta"></div>
    </section>

    <section class="card">
      <h2>全体サマリー</h2>
      <div class="kpis" id="kpis"></div>
    </section>

    <section class="card grid2">
      <div>
        <h2>月別 user メッセージ</h2>
        <div class="small-table-wrap">
          <table>
            <thead><tr><th>month</th><th>user_messages</th><th>conversations</th><th>active_days</th></tr></thead>
            <tbody id="monthlyBody"></tbody>
          </table>
        </div>
      </div>
      <div>
        <h2>日別 上位会話</h2>
        <label for="daySelect">日付</label>
        <select id="daySelect"></select>
        <div class="small-table-wrap" style="margin-top:8px">
          <table>
            <thead><tr><th>#</th><th>title</th><th>user</th><th>category</th></tr></thead>
            <tbody id="dailyTopBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>会話一覧</h2>
      <div class="controls">
        <div>
          <label for="titleSearch">タイトル検索</label>
          <input id="titleSearch" type="text" placeholder="部分一致で検索" />
        </div>
        <div>
          <label for="monthFilter">年月フィルタ</label>
          <select id="monthFilter"></select>
        </div>
        <div>
          <label for="categoryFilter">カテゴリフィルタ</label>
          <select id="categoryFilter"></select>
        </div>
        <div>
          <label for="sortBy">ソート</label>
          <select id="sortBy">
            <option value="messages_desc">メッセージ数順</option>
            <option value="last_desc">最終更新日順</option>
          </select>
        </div>
      </div>
      <p class="muted" id="filterMeta"></p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>conversation_id</th>
              <th>title</th>
              <th>category</th>
              <th>first_message_at</th>
              <th>last_message_at</th>
              <th>user</th>
              <th>assistant</th>
              <th>total</th>
              <th>active_days</th>
              <th>top_keywords</th>
            </tr>
          </thead>
          <tbody id="conversationBody"></tbody>
        </table>
      </div>
    </section>
  </div>

  <script id="data" type="application/json">__PAYLOAD__</script>
  <script>
    const DATA = JSON.parse(document.getElementById("data").textContent);
    const MONTHLY = (DATA.monthly || []).slice().sort((a,b)=>a.month.localeCompare(b.month));
    const DAILY = (DATA.daily || []).slice().sort((a,b)=>a.date.localeCompare(b.date));
    const DTC = DATA.daily_top_conversations || [];
    const INDEX = (DATA.conversation_index || []).slice();

    const formatNumber = (v) => Number(v || 0).toLocaleString();
    const normalize = (v) => String(v || "").toLowerCase();
    const monthOfIso = (iso) => {
      if (!iso || typeof iso !== "string" || iso.length < 7) return "";
      return iso.slice(0, 7);
    };

    const state = {
      titleSearch: "",
      monthFilter: "all",
      categoryFilter: "all",
      sortBy: "messages_desc",
      focusedConversationId: null,
      selectedDay: DAILY.length ? DAILY[DAILY.length - 1].date : null,
    };

    const dtcByDay = new Map();
    for (const row of DTC) {
      if (!dtcByDay.has(row.date)) dtcByDay.set(row.date, []);
      dtcByDay.get(row.date).push(row);
    }
    for (const rows of dtcByDay.values()) {
      rows.sort((a,b)=>a.rank-b.rank);
    }

    function renderHeader() {
      document.getElementById("tz").textContent = DATA.meta?.timezone || "unknown";
      const stats = DATA.meta?.stats || {};
      const topMeta = document.getElementById("topMeta");
      topMeta.innerHTML = [
        `入力会話オブジェクト: ${formatNumber(stats.total_conversation_objects || 0)}`,
        `ユニーク会話: ${formatNumber(stats.total_conversations || 0)}`,
        `ユニークメッセージ: ${formatNumber(stats.total_unique_messages || 0)}`,
        `重複除外: ${formatNumber(stats.total_duplicate_messages_skipped || 0)}`,
      ].map((x)=>`<span>${x}</span>`).join("");
    }

    function renderKpis() {
      const stats = DATA.meta?.stats || {};
      const totalUser = MONTHLY.reduce((acc, row) => acc + Number(row.user_messages || 0), 0);
      const totalActiveDays = MONTHLY.reduce((acc, row) => acc + Number(row.active_days || 0), 0);
      const peakDay = DAILY.length
        ? DAILY.reduce((best, row) => (Number(row.user_messages || 0) > Number(best.user_messages || 0) ? row : best), DAILY[0])
        : null;
      const cards = [
        ["total_unique_messages", formatNumber(stats.total_unique_messages || 0)],
        ["total_user_messages", formatNumber(totalUser)],
        ["total_active_days", formatNumber(totalActiveDays)],
        ["total_conversations", formatNumber(stats.total_conversations || INDEX.length)],
        ["peak_day", peakDay ? `${peakDay.date} (${formatNumber(peakDay.user_messages)})` : "-"],
      ];
      const root = document.getElementById("kpis");
      root.innerHTML = "";
      for (const [label, value] of cards) {
        const el = document.createElement("div");
        el.className = "kpi";
        el.innerHTML = `<div class="kpi-label">${label}</div><div class="kpi-value">${value}</div>`;
        root.appendChild(el);
      }
    }

    function renderMonthlyTable() {
      const body = document.getElementById("monthlyBody");
      body.innerHTML = "";
      if (!MONTHLY.length) {
        body.innerHTML = `<tr><td colspan="4" class="empty">データがありません</td></tr>`;
        return;
      }
      const maxUser = Math.max(...MONTHLY.map(r=>Number(r.user_messages || 0)), 1);
      for (const row of MONTHLY) {
        const tr = document.createElement("tr");
        const pct = Math.round((Number(row.user_messages || 0) / maxUser) * 100);
        tr.innerHTML = `
          <td class="mono">${row.month}</td>
          <td>
            <div>${formatNumber(row.user_messages)}</div>
            <div class="bar-line"><span style="width:${pct}%"></span></div>
          </td>
          <td>${formatNumber(row.conversations)}</td>
          <td>${formatNumber(row.active_days)}</td>
        `;
        body.appendChild(tr);
      }
    }

    function setupDaySelect() {
      const select = document.getElementById("daySelect");
      const days = DAILY.map(r => r.date);
      select.innerHTML = "";
      if (!days.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "データなし";
        select.appendChild(option);
        state.selectedDay = null;
        return;
      }
      for (const day of days) {
        const option = document.createElement("option");
        option.value = day;
        option.textContent = day;
        if (state.selectedDay === day) option.selected = true;
        select.appendChild(option);
      }
      if (!state.selectedDay || !days.includes(state.selectedDay)) {
        state.selectedDay = days[days.length - 1];
        select.value = state.selectedDay;
      }
      select.onchange = () => {
        state.selectedDay = select.value;
        renderDailyTop();
      };
    }

    function renderDailyTop() {
      const body = document.getElementById("dailyTopBody");
      body.innerHTML = "";
      if (!state.selectedDay) {
        body.innerHTML = `<tr><td colspan="4" class="empty">日付を選択してください</td></tr>`;
        return;
      }
      const rows = dtcByDay.get(state.selectedDay) || [];
      if (!rows.length) {
        body.innerHTML = `<tr><td colspan="4" class="empty">この日の会話データはありません</td></tr>`;
        return;
      }
      for (const row of rows) {
        const tr = document.createElement("tr");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "link-btn";
        button.textContent = row.title || row.conversation_id;
        button.addEventListener("click", () => {
          state.focusedConversationId = row.conversation_id;
          const month = monthOfIso((INDEX.find(x=>x.conversation_id===row.conversation_id) || {}).last_message_at || "");
          if (month) {
            const monthSelect = document.getElementById("monthFilter");
            state.monthFilter = month;
            monthSelect.value = month;
          }
          renderConversationTable();
          const targetRow = document.querySelector(`tr[data-conv-id="${CSS.escape(row.conversation_id)}"]`);
          if (targetRow) {
            targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        });

        const titleTd = document.createElement("td");
        titleTd.appendChild(button);

        tr.innerHTML = `<td>${row.rank}</td><td></td><td>${formatNumber(row.user_messages)}</td><td>${row.inferred_category || ""}</td>`;
        tr.children[1].replaceWith(titleTd);
        body.appendChild(tr);
      }
    }

    function setupFilters() {
      const titleSearch = document.getElementById("titleSearch");
      const monthFilter = document.getElementById("monthFilter");
      const categoryFilter = document.getElementById("categoryFilter");
      const sortBy = document.getElementById("sortBy");

      const months = Array.from(new Set(INDEX.map(row => monthOfIso(row.last_message_at)).filter(Boolean))).sort();
      const categories = Array.from(new Set(INDEX.map(row => row.inferred_category || "その他"))).sort();

      monthFilter.innerHTML = `<option value="all">すべて</option>` + months.map(m => `<option value="${m}">${m}</option>`).join("");
      categoryFilter.innerHTML = `<option value="all">すべて</option>` + categories.map(c => `<option value="${c}">${c}</option>`).join("");

      titleSearch.oninput = () => {
        state.titleSearch = titleSearch.value;
        renderConversationTable();
      };
      monthFilter.onchange = () => {
        state.monthFilter = monthFilter.value;
        renderConversationTable();
      };
      categoryFilter.onchange = () => {
        state.categoryFilter = categoryFilter.value;
        renderConversationTable();
      };
      sortBy.onchange = () => {
        state.sortBy = sortBy.value;
        renderConversationTable();
      };
    }

    function filterAndSortIndex() {
      let rows = INDEX.slice();
      const q = normalize(state.titleSearch);
      if (q) {
        rows = rows.filter(row => normalize(row.title).includes(q));
      }
      if (state.monthFilter !== "all") {
        rows = rows.filter(row => monthOfIso(row.last_message_at) === state.monthFilter);
      }
      if (state.categoryFilter !== "all") {
        rows = rows.filter(row => (row.inferred_category || "その他") === state.categoryFilter);
      }

      rows.sort((a,b) => {
        if (state.sortBy === "last_desc") {
          const av = a.last_message_at || "";
          const bv = b.last_message_at || "";
          if (av !== bv) return bv.localeCompare(av);
          return Number(b.total_message_count || 0) - Number(a.total_message_count || 0);
        }
        const byTotal = Number(b.total_message_count || 0) - Number(a.total_message_count || 0);
        if (byTotal !== 0) return byTotal;
        return (b.last_message_at || "").localeCompare(a.last_message_at || "");
      });
      return rows;
    }

    function renderConversationTable() {
      const rows = filterAndSortIndex();
      const body = document.getElementById("conversationBody");
      body.innerHTML = "";

      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.dataset.convId = row.conversation_id;
        if (state.focusedConversationId && row.conversation_id === state.focusedConversationId) {
          tr.classList.add("row-highlight");
        }
        const keywords = Array.isArray(row.top_keywords) ? row.top_keywords : [];
        tr.innerHTML = `
          <td class="mono">${row.conversation_id}</td>
          <td>${row.title || ""}</td>
          <td><span class="chip">${row.inferred_category || "その他"}</span></td>
          <td class="mono">${row.first_message_at || ""}</td>
          <td class="mono">${row.last_message_at || ""}</td>
          <td>${formatNumber(row.user_message_count)}</td>
          <td>${formatNumber(row.assistant_message_count)}</td>
          <td>${formatNumber(row.total_message_count)}</td>
          <td>${formatNumber(row.active_days)}</td>
          <td>${keywords.join(", ")}</td>
        `;
        body.appendChild(tr);
      }

      if (!rows.length) {
        body.innerHTML = `<tr><td colspan="10" class="empty">条件に一致する会話がありません</td></tr>`;
      }

      document.getElementById("filterMeta").textContent = `表示件数: ${formatNumber(rows.length)} / 全${formatNumber(INDEX.length)}件`;
    }

    function render() {
      renderHeader();
      renderKpis();
      renderMonthlyTable();
      setupDaySelect();
      renderDailyTop();
      setupFilters();
      renderConversationTable();
    }

    render();
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD__", payload)


def write_dashboard_html(path: Path, parsed: dict) -> None:
    path.write_text(build_dashboard_html(parsed), encoding="utf-8")


def load_parsed(path: Path) -> dict:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not has_required_parsed_shape(parsed):
        raise ValueError("parsed_summary.json exists but schema is incompatible.")
    return parsed


def write_outputs(output_dir: Path, parsed: dict) -> None:
    monthly = sorted(parsed["monthly"], key=lambda r: r["month"])
    daily = sorted(parsed["daily"], key=lambda r: r["date"])
    daily_hourly = sorted(parsed["daily_hourly"], key=lambda r: (r["date"], r["hour"]))
    conversation_index = parsed.get("conversation_index", [])
    category_monthly = sorted(
        parsed.get("category_monthly", []), key=lambda r: (r["month"], r["category"])
    )
    category_daily = sorted(
        parsed.get("category_daily", []), key=lambda r: (r["date"], r["category"])
    )
    keywords_monthly = sorted(
        parsed.get("keywords_monthly", []),
        key=lambda r: (r["month"], -r["count"], r["keyword"]),
    )

    write_csv(
        output_dir / "monthly_user_messages.csv",
        ["month", "user_messages"],
        [[r["month"], r["user_messages"]] for r in monthly],
    )
    write_csv(
        output_dir / "monthly_conversations.csv",
        ["month", "conversations"],
        [[r["month"], r["conversations"]] for r in monthly],
    )
    write_csv(
        output_dir / "monthly_active_days.csv",
        ["month", "active_days"],
        [[r["month"], r["active_days"]] for r in monthly],
    )
    write_csv(
        output_dir / "daily_user_messages.csv",
        ["date", "user_messages"],
        [[r["date"], r["user_messages"]] for r in daily],
    )
    write_csv(
        output_dir / "daily_hourly_user_messages.csv",
        ["date", "hour", "user_messages"],
        [[r["date"], r["hour"], r["user_messages"]] for r in daily_hourly],
    )
    write_csv(
        output_dir / "daily_conversations.csv",
        ["date", "conversations"],
        [[r["date"], r["conversations"]] for r in daily],
    )

    write_csv(
        output_dir / "conversations_index.csv",
        [
            "conversation_id",
            "title",
            "first_message_at",
            "last_message_at",
            "user_message_count",
            "assistant_message_count",
            "total_message_count",
            "active_days",
            "inferred_category",
            "top_keywords",
        ],
        [
            [
                row.get("conversation_id", ""),
                row.get("title", ""),
                row.get("first_message_at", ""),
                row.get("last_message_at", ""),
                row.get("user_message_count", 0),
                row.get("assistant_message_count", 0),
                row.get("total_message_count", 0),
                row.get("active_days", 0),
                row.get("inferred_category", ""),
                "|".join(
                    row.get("top_keywords", [])
                    if isinstance(row.get("top_keywords"), list)
                    else []
                ),
            ]
            for row in conversation_index
        ],
    )

    write_csv(
        output_dir / "category_monthly.csv",
        [
            "month",
            "category",
            "total_message_count",
            "user_message_count",
            "assistant_message_count",
            "conversation_count",
        ],
        [
            [
                row["month"],
                row["category"],
                row["total_message_count"],
                row["user_message_count"],
                row["assistant_message_count"],
                row["conversation_count"],
            ]
            for row in category_monthly
        ],
    )

    write_csv(
        output_dir / "category_daily.csv",
        [
            "date",
            "category",
            "total_message_count",
            "user_message_count",
            "assistant_message_count",
            "conversation_count",
        ],
        [
            [
                row["date"],
                row["category"],
                row["total_message_count"],
                row["user_message_count"],
                row["assistant_message_count"],
                row["conversation_count"],
            ]
            for row in category_daily
        ],
    )

    write_csv(
        output_dir / "keywords_monthly.csv",
        ["month", "keyword", "count"],
        [[row["month"], row["keyword"], row["count"]] for row in keywords_monthly],
    )

    (output_dir / "parsed_summary.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_monthly_summary_md(output_dir / "monthly_summary.md", parsed)
    write_dashboard_html(output_dir / "dashboard.html", parsed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze ChatGPT export and generate static dashboard outputs."
    )
    parser.add_argument("--input-dir", default=".", help="Directory containing export files")
    parser.add_argument("--output-dir", default=".", help="Directory for generated outputs")
    parser.add_argument(
        "--timezone", default="Asia/Tokyo", help="IANA timezone (default: Asia/Tokyo)"
    )
    parser.add_argument(
        "--rules",
        default=str(DEFAULT_CATEGORY_RULES_PATH),
        help="Path to category keyword rules JSON",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force reparsing raw export even if parsed_summary.json is reusable",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rules_path = Path(args.rules).resolve()
    if not rules_path.exists():
        raise FileNotFoundError(f"Category rules not found: {rules_path}")

    rules = load_category_rules(rules_path)
    rules["rules_path"] = str(rules_path)

    input_files, marker = detect_inputs(input_dir)
    parsed_path = output_dir / "parsed_summary.json"

    if not args.rebuild and should_reuse_parsed(parsed_path, input_files, rules_path):
        parsed = load_parsed(parsed_path)
        parse_mode = "reused parsed_summary.json"
    else:
        local_tz = ensure_timezone(args.timezone)
        parsed = collect_stats_from_inputs(input_files, marker, local_tz, rules)
        parse_mode = "parsed raw export"

    parsed.setdefault("meta", {})
    parsed["meta"]["timezone"] = args.timezone
    parsed["meta"]["input_files"] = [str(p) for p in input_files]
    parsed["meta"]["rules_file"] = str(rules_path)
    parsed["meta"]["generated_at"] = datetime.now().astimezone().isoformat()

    write_outputs(output_dir, parsed)

    print(f"Mode: {parse_mode}")
    print("Input files:")
    for path in input_files:
        print(f"  - {path}")
    print("Output files:")
    for name in (
        "dashboard.html",
        "monthly_user_messages.csv",
        "monthly_conversations.csv",
        "monthly_active_days.csv",
        "daily_user_messages.csv",
        "daily_hourly_user_messages.csv",
        "daily_conversations.csv",
        "conversations_index.csv",
        "category_monthly.csv",
        "category_daily.csv",
        "keywords_monthly.csv",
        "parsed_summary.json",
        "monthly_summary.md",
    ):
        print(f"  - {output_dir / name}")


if __name__ == "__main__":
    main()
