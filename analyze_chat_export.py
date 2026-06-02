#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import difflib
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

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
MONTHLY_REQUIRED_KEYS = (
    "avg_per_elapsed_day",
    "avg_per_active_day",
    "median_daily_user_messages",
    "peak_daily_user_messages",
    "peak_daily_date",
)
DEFAULT_CATEGORY_RULES_PATH = Path("rules/category_keywords.json")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+#./-]{2,}|[縺・繧薙ぃ-繝ｶ繝ｼ荳-鮴]{2,}")
DEFAULT_CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
DEFAULT_MATCH_MONTH = "2026-04"
JST = timezone(timedelta(hours=9), name="Asia/Tokyo")
CODEX_PROMPT_HINTS = (
    "you are",
    "codex",
    "target repository:",
    "repository:",
    "objective:",
    "purpose:",
    "context:",
    "todo:",
    "tasks:",
    "prohibited",
    "success criteria",
    "final report",
    "changed files",
    "verification",
    "ai review request",
    "ai_review_request_id",
    "repository",
    "review questions",
    "do not implement code",
)
ASSISTANT_PROMPT_START_HINTS = (
    "you are",
    "target repository:",
    "repository:",
    "objective:",
    "purpose:",
    "ai review request",
)


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
    if not (isinstance(parsed, dict) and all(k in parsed for k in PARSED_REQUIRED_KEYS)):
        return False
    monthly = parsed.get("monthly")
    if not isinstance(monthly, list):
        return False
    for row in monthly[:3]:
        if not isinstance(row, dict):
            return False
        if not all(k in row for k in MONTHLY_REQUIRED_KEYS):
            return False
    return True


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


def fallback_token_estimate(text: str) -> int:
    stripped = (text or "").strip()
    if not stripped:
        return 0
    ascii_chars = sum(1 for ch in stripped if ord(ch) < 128)
    non_ascii_chars = len(stripped) - ascii_chars
    # Rough estimate: ASCII text is denser than CJK text.
    estimated = (ascii_chars / 4.0) + float(non_ascii_chars)
    return max(1, int(round(estimated)))


def build_token_estimator() -> tuple[Callable[[str], int], str]:
    try:
        import tiktoken  # type: ignore

        encoding = tiktoken.get_encoding("o200k_base")

        def estimate_with_tiktoken(text: str) -> int:
            stripped = (text or "").strip()
            if not stripped:
                return 0
            return len(encoding.encode(stripped, disallowed_special=()))

        return estimate_with_tiktoken, "tiktoken:o200k_base"
    except Exception:
        return fallback_token_estimate, "char_fallback_v1"


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


def month_total_days(month: str) -> int:
    year = int(month[:4])
    mon = int(month[5:7])
    return calendar.monthrange(year, mon)[1]


def median_value(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def parse_month_range_jst(month: str) -> tuple[datetime, datetime]:
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise ValueError(f"Invalid month format: {month}")
    year = int(month[:4])
    mon = int(month[5:7])
    if mon < 1 or mon > 12:
        raise ValueError(f"Invalid month value: {month}")
    start = datetime(year, mon, 1, 0, 0, 0, tzinfo=JST)
    if mon == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=JST)
    else:
        end = datetime(year, mon + 1, 1, 0, 0, 0, tzinfo=JST)
    return start, end


def sha256_hex(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_snippet(text: str, limit: int = 140) -> str:
    compact = re.sub(r"\s+", " ", (text or "").strip())
    if len(compact) <= limit:
        return compact
    if limit < 10:
        return compact[:limit]
    return compact[: limit - 3] + "..."


def extract_repo_hint(text: str) -> str:
    if not text:
        return ""
    path_match = re.search(r"[A-Za-z]:\\[A-Za-z0-9_.\-\\]+", text)
    if path_match:
        return path_match.group(0).rstrip("\\")
    repo_line = re.search(
        r"(?im)^(?:target repository|repository|repo|cwd_or_repo|cwd)\s*[:：]\s*(.+?)\s*$",
        text,
    )
    if repo_line:
        return repo_line.group(1).strip()[:240]
    return ""


def strip_markdown_fences(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"```[^\n]*\n(.*?)```", lambda m: m.group(1), text, flags=re.S)


def normalize_prompt_text(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = unicodedata.normalize("NFKC", value)
    value = strip_markdown_fences(value)
    value = re.sub(r"\\{2,}", r"\\", value)
    value = re.sub(r"(?m)^\s*>+\s?", "", value)
    value = re.sub(r"[`*_~]+", "", value)
    value = re.sub(r'[\"\'“”‘’「」『』]+', "", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"(?is)\n+(?:note|notes|please adjust|you can edit this prompt).*$", "", value)
    value = "\n".join(line.strip() for line in value.split("\n"))
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def count_prompt_hints(text: str) -> int:
    lowered = (text or "").lower()
    return sum(1 for hint in CODEX_PROMPT_HINTS if hint in lowered)


def is_codex_prompt_candidate(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 80:
        return False
    lowered = stripped.lower()
    if "codex" not in lowered and "ai review request" not in lowered and "do not implement code" not in lowered:
        return False
    section_hits = 0
    for marker in (
        "purpose:",
        "objective:",
        "target repository:",
        "repository:",
        "tasks:",
        "todo:",
        "review questions",
        "success criteria",
        "do not implement code",
        "目的:",
        "やること:",
        "前提:",
        "成功条件:",
        "禁止事項:",
        "変更ファイル一覧",
    ):
        if marker in lowered:
            section_hits += 1
    return section_hits >= 2


def estimate_prompt_confidence(text: str) -> float:
    stripped = (text or "").strip()
    hint_count = count_prompt_hints(stripped)
    confidence = 0.35 + min(0.45, hint_count * 0.11)
    if stripped.lower().startswith("you are") or stripped.startswith("あなたは"):
        confidence += 0.1
    if "objective:" in stripped.lower() or "tasks:" in stripped.lower() or "目的:" in stripped:
        confidence += 0.08
    if "ai review request" in stripped.lower():
        confidence += 0.08
    if len(stripped) > 400:
        confidence += 0.05
    return round(min(0.99, confidence), 3)


def extract_codex_prompt_candidates_from_assistant(text: str) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []

    candidates: list[str] = []
    for match in re.finditer(r"```[^\n]*\n(.*?)```", body, flags=re.S):
        block = (match.group(1) or "").strip()
        if is_codex_prompt_candidate(block):
            candidates.append(block)

    if candidates:
        pass
    elif is_codex_prompt_candidate(body):
        candidates.append(body)
    else:
        lines = body.splitlines()
        starts = []
        for idx, line in enumerate(lines):
            lowered = line.strip().lower()
            if not lowered:
                continue
            if any(lowered.startswith(hint) for hint in ASSISTANT_PROMPT_START_HINTS):
                starts.append(idx)
        for s_idx, start in enumerate(starts):
            end = starts[s_idx + 1] if s_idx + 1 < len(starts) else len(lines)
            chunk = "\n".join(lines[start:end]).strip()
            if is_codex_prompt_candidate(chunk):
                candidates.append(chunk)

    # Keep order but drop exact duplicates.
    unique: list[str] = []
    seen = set()
    for candidate in candidates:
        key = sha256_hex(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def in_range_jst(dt: datetime, start_jst: datetime, end_jst: datetime) -> bool:
    return start_jst <= dt < end_jst


def parse_iso8601_to_tz(value: str, tz_obj) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz_obj)


def extract_text_from_response_content(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


def is_injected_or_sensitive_prompt(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered.strip():
        return True
    if lowered.startswith("# agents.md instructions"):
        return True
    if "<instructions>" in lowered and "agents.md" in lowered:
        return True
    if "you are codex, a coding agent" in lowered:
        return True
    if "filesystem sandboxing" in lowered and "approval policy" in lowered:
        return True
    if "sandbox_mode" in lowered and "writable roots" in lowered:
        return True
    if "auth.json" in lowered or ".sandbox-secrets" in lowered:
        return True
    if ("secret" in lowered or "api key" in lowered or "token" in lowered or "auth" in lowered) and (
        "instruction" in lowered or "permission" in lowered or "sandbox" in lowered
    ):
        return True
    return False


def collect_chat_codex_prompts(
    paths: Iterable[Path],
    marker: Optional[str],
    local_tz,
    start_jst: datetime,
    end_jst: datetime,
) -> list[dict]:
    prompts: list[dict] = []
    seen_message_keys: set[str] = set()
    total_conversation_objects = 0
    prompt_index = 1

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
                if role != "assistant":
                    continue

                text = extract_message_text(message)
                msg_key = build_message_dedupe_key(conv_id, message, role, text)
                if msg_key in seen_message_keys:
                    continue
                seen_message_keys.add(msg_key)

                ts = pick_timestamp(message)
                if ts is None:
                    continue
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz)
                if not in_range_jst(dt, start_jst, end_jst):
                    continue

                candidates = extract_codex_prompt_candidates_from_assistant(text)
                if not candidates:
                    continue

                message_id = message.get("id")
                if not isinstance(message_id, str) or not message_id.strip():
                    node_id = node.get("id")
                    message_id = str(node_id) if node_id else ""

                for prompt_text in candidates:
                    if len(prompt_text) > 20000:
                        continue
                    normalized = normalize_prompt_text(prompt_text)
                    if not normalized:
                        continue
                    prompts.append(
                        {
                            "chat_prompt_id": f"chat-{prompt_index:06d}",
                            "date_jst": dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "date_key": dt.strftime("%Y-%m-%d"),
                            "conversation_id": conv_id,
                            "conversation_title": title,
                            "message_id": message_id,
                            "prompt_text": prompt_text,
                            "prompt_hash": sha256_hex(prompt_text),
                            "normalized_prompt_text": normalized,
                            "normalized_hash": sha256_hex(normalized),
                            "snippet": build_snippet(prompt_text),
                            "estimated_repo": extract_repo_hint(prompt_text),
                            "confidence": estimate_prompt_confidence(prompt_text),
                            "_dt": dt,
                        }
                    )
                    prompt_index += 1

    prompts.sort(key=lambda row: (row["date_jst"], row["chat_prompt_id"]))
    return prompts


def collect_rollout_files(codex_sessions_root: Path, month: str) -> list[Path]:
    month_path = codex_sessions_root / month[:4] / month[5:7]
    if not month_path.exists():
        return []
    return sorted(month_path.glob("**/rollout-*.jsonl"))


def collect_codex_user_prompts(
    rollout_paths: Iterable[Path],
    local_tz,
    start_jst: datetime,
    end_jst: datetime,
) -> list[dict]:
    prompts: list[dict] = []
    prompt_index = 1

    for rollout_path in rollout_paths:
        session_id = rollout_path.stem.replace("rollout-", "")
        cwd_hint = ""
        primary_seen_hashes: set[str] = set()
        secondary_buffer: list[tuple[int, datetime, str]] = []

        with rollout_path.open("r", encoding="utf-8") as f:
            for event_index, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue

                record_type = record.get("type")
                event_type = payload.get("type")
                ts = parse_iso8601_to_tz(str(record.get("timestamp") or ""), local_tz)
                if ts is None:
                    continue
                if not in_range_jst(ts, start_jst, end_jst):
                    continue

                if record_type == "session_meta":
                    sid = payload.get("id")
                    if isinstance(sid, str) and sid.strip():
                        session_id = sid.strip()
                    cwd = payload.get("cwd")
                    if isinstance(cwd, str) and cwd.strip():
                        cwd_hint = cwd.strip()
                    continue

                if record_type == "event_msg" and event_type == "user_message":
                    text = payload.get("message")
                    if not isinstance(text, str):
                        text = ""
                    text = text.strip()
                    if not text or is_injected_or_sensitive_prompt(text):
                        continue
                    normalized = normalize_prompt_text(text)
                    if not normalized:
                        continue
                    primary_seen_hashes.add(sha256_hex(normalized))
                    prompts.append(
                        {
                            "codex_prompt_id": f"codex-{prompt_index:06d}",
                            "date_jst": ts.strftime("%Y-%m-%d %H:%M:%S"),
                            "date_key": ts.strftime("%Y-%m-%d"),
                            "rollout_path": str(rollout_path),
                            "session_id": session_id,
                            "event_index": event_index,
                            "prompt_text": text,
                            "prompt_hash": sha256_hex(text),
                            "normalized_prompt_text": normalized,
                            "normalized_hash": sha256_hex(normalized),
                            "snippet": build_snippet(text),
                            "cwd_or_repo": cwd_hint,
                            "confidence": 1.0,
                            "_dt": ts,
                        }
                    )
                    prompt_index += 1
                    continue

                if record_type == "response_item":
                    if event_type == "message" and str(payload.get("role") or "").lower() == "user":
                        text = extract_text_from_response_content(payload.get("content"))
                        if not text or is_injected_or_sensitive_prompt(text):
                            continue
                        secondary_buffer.append((event_index, ts, text))

        # Secondary source is used only when primary records do not have the same normalized text.
        for event_index, ts, text in secondary_buffer:
            normalized = normalize_prompt_text(text)
            if not normalized:
                continue
            if sha256_hex(normalized) in primary_seen_hashes:
                continue
            prompts.append(
                {
                    "codex_prompt_id": f"codex-{prompt_index:06d}",
                    "date_jst": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_key": ts.strftime("%Y-%m-%d"),
                    "rollout_path": str(rollout_path),
                    "session_id": session_id,
                    "event_index": event_index,
                    "prompt_text": text,
                    "prompt_hash": sha256_hex(text),
                    "normalized_prompt_text": normalized,
                    "normalized_hash": sha256_hex(normalized),
                    "snippet": build_snippet(text),
                    "cwd_or_repo": cwd_hint,
                    "confidence": 0.8,
                    "_dt": ts,
                }
            )
            prompt_index += 1

    prompts.sort(key=lambda row: (row["date_jst"], row["rollout_path"], row["event_index"]))
    return prompts


def split_path_tail(path_value: str, max_len: int = 80) -> str:
    value = (path_value or "").strip()
    if len(value) <= max_len:
        return value
    return "..." + value[-(max_len - 3) :]


def build_match_score(chat: dict, codex: dict) -> tuple[float, float]:
    ratio = difflib.SequenceMatcher(
        None,
        chat.get("normalized_prompt_text", ""),
        codex.get("normalized_prompt_text", ""),
    ).ratio()
    chat_repo = (chat.get("estimated_repo") or "").lower()
    codex_repo = (codex.get("cwd_or_repo") or "").lower()
    repo_bonus = 0.0
    if chat_repo and codex_repo and (chat_repo in codex_repo or codex_repo in chat_repo):
        repo_bonus = 0.04
    gap_hours = abs((chat["_dt"] - codex["_dt"]).total_seconds()) / 3600.0
    time_penalty = min(0.08, gap_hours * 0.0015)
    score = ratio + repo_bonus - time_penalty
    return score, ratio


def match_chat_and_codex_prompts(chat_prompts: list[dict], codex_prompts: list[dict]) -> dict:
    matches: list[dict] = []
    chat_unmatched = {row["chat_prompt_id"]: row for row in chat_prompts}
    codex_unmatched = {row["codex_prompt_id"]: row for row in codex_prompts}

    chat_by_hash: Dict[str, list[dict]] = defaultdict(list)
    codex_by_hash: Dict[str, list[dict]] = defaultdict(list)
    for row in chat_prompts:
        chat_by_hash[row["normalized_hash"]].append(row)
    for row in codex_prompts:
        codex_by_hash[row["normalized_hash"]].append(row)

    match_index = 1
    for normalized_hash, chat_rows in chat_by_hash.items():
        codex_rows = codex_by_hash.get(normalized_hash)
        if not codex_rows:
            continue
        ordered_chat = sorted(chat_rows, key=lambda r: r["_dt"])
        ordered_codex = sorted(codex_rows, key=lambda r: r["_dt"])
        pair_count = min(len(ordered_chat), len(ordered_codex))
        for idx in range(pair_count):
            chat_row = ordered_chat[idx]
            codex_row = ordered_codex[idx]
            matches.append(
                {
                    "match_id": f"match-{match_index:06d}",
                    "match_type": "exact_match",
                    "confidence": 1.0,
                    "similarity": 1.0,
                    "chat_prompt_id": chat_row["chat_prompt_id"],
                    "codex_prompt_id": codex_row["codex_prompt_id"],
                    "date_jst": chat_row["date_jst"],
                    "date_key": chat_row["date_key"],
                    "conversation_title": chat_row.get("conversation_title", ""),
                    "rollout_path": codex_row.get("rollout_path", ""),
                    "estimated_repo": chat_row.get("estimated_repo", ""),
                    "cwd_or_repo": codex_row.get("cwd_or_repo", ""),
                    "snippet": chat_row.get("snippet", ""),
                }
            )
            chat_unmatched.pop(chat_row["chat_prompt_id"], None)
            codex_unmatched.pop(codex_row["codex_prompt_id"], None)
            match_index += 1

    candidate_pairs = []
    for chat_row in chat_unmatched.values():
        chat_text = chat_row.get("normalized_prompt_text", "")
        chat_len = len(chat_text)
        for codex_row in codex_unmatched.values():
            codex_text = codex_row.get("normalized_prompt_text", "")
            codex_len = len(codex_text)
            if not chat_len or not codex_len:
                continue
            if min(chat_len, codex_len) / max(chat_len, codex_len) < 0.45:
                continue
            if abs((chat_row["_dt"] - codex_row["_dt"]).total_seconds()) > 14 * 24 * 3600:
                continue
            score, ratio = build_match_score(chat_row, codex_row)
            if ratio < 0.88:
                continue
            candidate_pairs.append((score, ratio, chat_row["chat_prompt_id"], codex_row["codex_prompt_id"]))
    candidate_pairs.sort(reverse=True, key=lambda row: row[0])

    used_chat = set()
    used_codex = set()
    for score, ratio, chat_id, codex_id in candidate_pairs:
        if chat_id in used_chat or codex_id in used_codex:
            continue
        chat_row = chat_unmatched.get(chat_id)
        codex_row = codex_unmatched.get(codex_id)
        if chat_row is None or codex_row is None:
            continue
        used_chat.add(chat_id)
        used_codex.add(codex_id)
        matches.append(
            {
                "match_id": f"match-{match_index:06d}",
                "match_type": "near_match",
                "confidence": round(max(0.0, min(0.99, score)), 3),
                "similarity": round(ratio, 3),
                "chat_prompt_id": chat_row["chat_prompt_id"],
                "codex_prompt_id": codex_row["codex_prompt_id"],
                "date_jst": chat_row["date_jst"],
                "date_key": chat_row["date_key"],
                "conversation_title": chat_row.get("conversation_title", ""),
                "rollout_path": codex_row.get("rollout_path", ""),
                "estimated_repo": chat_row.get("estimated_repo", ""),
                "cwd_or_repo": codex_row.get("cwd_or_repo", ""),
                "snippet": chat_row.get("snippet", ""),
            }
        )
        chat_unmatched.pop(chat_id, None)
        codex_unmatched.pop(codex_id, None)
        match_index += 1

    matches.sort(key=lambda row: (row["date_jst"], row["match_type"], row["match_id"]))
    unmatched_chat = sorted(chat_unmatched.values(), key=lambda row: (row["date_jst"], row["chat_prompt_id"]))
    unmatched_codex = sorted(
        codex_unmatched.values(),
        key=lambda row: (row["date_jst"], row["rollout_path"], row["event_index"]),
    )
    return {
        "matches": matches,
        "unmatched_chat": unmatched_chat,
        "unmatched_codex": unmatched_codex,
    }


def aggregate_daily_counts(chat_prompts: list[dict], codex_prompts: list[dict], matches: list[dict]) -> list[dict]:
    day_rows: Dict[str, dict] = defaultdict(
        lambda: {
            "date_jst": "",
            "chat_codex_prompt_count": 0,
            "codex_user_prompt_count": 0,
            "matched_prompt_count": 0,
            "chat_only_prompt_count": 0,
            "codex_only_prompt_count": 0,
        }
    )

    for row in chat_prompts:
        day = row["date_key"]
        acc = day_rows[day]
        acc["date_jst"] = day
        acc["chat_codex_prompt_count"] += 1
    for row in codex_prompts:
        day = row["date_key"]
        acc = day_rows[day]
        acc["date_jst"] = day
        acc["codex_user_prompt_count"] += 1
    for row in matches:
        day = row["date_key"]
        acc = day_rows[day]
        acc["date_jst"] = day
        acc["matched_prompt_count"] += 1

    for day, acc in day_rows.items():
        acc["chat_only_prompt_count"] = acc["chat_codex_prompt_count"] - acc["matched_prompt_count"]
        acc["codex_only_prompt_count"] = acc["codex_user_prompt_count"] - acc["matched_prompt_count"]

    return [day_rows[day] for day in sorted(day_rows.keys())]


def aggregate_repo_counts(chat_prompts: list[dict], codex_prompts: list[dict], matches: list[dict]) -> list[dict]:
    rows: Dict[str, dict] = defaultdict(
        lambda: {
            "repo_or_path": "",
            "chat_codex_prompt_count": 0,
            "codex_user_prompt_count": 0,
            "matched_prompt_count": 0,
            "chat_only_prompt_count": 0,
            "codex_only_prompt_count": 0,
        }
    )

    def repo_key(value: str) -> str:
        stripped = (value or "").strip()
        return stripped if stripped else "(unknown)"

    for row in chat_prompts:
        key = repo_key(row.get("estimated_repo", ""))
        acc = rows[key]
        acc["repo_or_path"] = key
        acc["chat_codex_prompt_count"] += 1
    for row in codex_prompts:
        key = repo_key(row.get("cwd_or_repo", ""))
        acc = rows[key]
        acc["repo_or_path"] = key
        acc["codex_user_prompt_count"] += 1
    for row in matches:
        keys = {
            repo_key(row.get("estimated_repo", "")),
            repo_key(row.get("cwd_or_repo", "")),
        }
        for key in keys:
            if key == "(unknown)":
                continue
            acc = rows[key]
            acc["repo_or_path"] = key
            acc["matched_prompt_count"] += 1

    for key, acc in rows.items():
        acc["chat_only_prompt_count"] = acc["chat_codex_prompt_count"] - acc["matched_prompt_count"]
        acc["codex_only_prompt_count"] = acc["codex_user_prompt_count"] - acc["matched_prompt_count"]
        if key == "(unknown)" and not (
            acc["chat_codex_prompt_count"] or acc["codex_user_prompt_count"] or acc["matched_prompt_count"]
        ):
            continue

    return sorted(rows.values(), key=lambda row: row["repo_or_path"].lower())


def aggregate_conversation_counts(chat_prompts: list[dict], matches: list[dict]) -> list[dict]:
    matched_chat_ids = {row["chat_prompt_id"] for row in matches}
    rows: Dict[str, dict] = defaultdict(
        lambda: {
            "conversation_title": "",
            "chat_codex_prompt_count": 0,
            "matched_prompt_count": 0,
            "chat_only_prompt_count": 0,
        }
    )

    for row in chat_prompts:
        title = row.get("conversation_title", "") or "(untitled)"
        acc = rows[title]
        acc["conversation_title"] = title
        acc["chat_codex_prompt_count"] += 1
        if row["chat_prompt_id"] in matched_chat_ids:
            acc["matched_prompt_count"] += 1

    for acc in rows.values():
        acc["chat_only_prompt_count"] = acc["chat_codex_prompt_count"] - acc["matched_prompt_count"]

    return sorted(rows.values(), key=lambda row: (-row["chat_codex_prompt_count"], row["conversation_title"]))


def aggregate_rollout_counts(codex_prompts: list[dict], matches: list[dict]) -> list[dict]:
    matched_codex_ids = {row["codex_prompt_id"] for row in matches}
    rows: Dict[str, dict] = defaultdict(
        lambda: {
            "rollout_path": "",
            "codex_user_prompt_count": 0,
            "matched_prompt_count": 0,
            "codex_only_prompt_count": 0,
        }
    )

    for row in codex_prompts:
        rollout = row.get("rollout_path", "")
        acc = rows[rollout]
        acc["rollout_path"] = rollout
        acc["codex_user_prompt_count"] += 1
        if row["codex_prompt_id"] in matched_codex_ids:
            acc["matched_prompt_count"] += 1

    for acc in rows.values():
        acc["codex_only_prompt_count"] = acc["codex_user_prompt_count"] - acc["matched_prompt_count"]

    return sorted(rows.values(), key=lambda row: (-row["codex_user_prompt_count"], row["rollout_path"]))


def build_codex_match_report(
    input_paths: Iterable[Path],
    marker: Optional[str],
    local_tz,
    codex_sessions_root: Path,
    month: str,
) -> dict:
    start_jst, end_jst = parse_month_range_jst(month)
    chat_prompts = collect_chat_codex_prompts(input_paths, marker, local_tz, start_jst, end_jst)
    rollout_paths = collect_rollout_files(codex_sessions_root, month)
    codex_prompts = collect_codex_user_prompts(rollout_paths, local_tz, start_jst, end_jst)

    match_result = match_chat_and_codex_prompts(chat_prompts, codex_prompts)
    matches = match_result["matches"]
    unmatched_chat = match_result["unmatched_chat"]
    unmatched_codex = match_result["unmatched_codex"]

    exact_count = sum(1 for row in matches if row["match_type"] == "exact_match")
    near_count = sum(1 for row in matches if row["match_type"] == "near_match")

    summary = {
        "month": month,
        "range_start_jst": start_jst.strftime("%Y-%m-%d %H:%M:%S"),
        "range_end_jst": end_jst.strftime("%Y-%m-%d %H:%M:%S"),
        "chat_codex_prompt_count": len(chat_prompts),
        "codex_user_prompt_count": len(codex_prompts),
        "matched_prompt_count": len(matches),
        "chat_only_prompt_count": len(unmatched_chat),
        "codex_only_prompt_count": len(unmatched_codex),
        "exact_match_count": exact_count,
        "near_match_count": near_count,
    }

    def drop_internal(rows: list[dict]) -> list[dict]:
        sanitized = []
        for row in rows:
            item = {k: v for k, v in row.items() if not k.startswith("_")}
            sanitized.append(item)
        return sanitized

    return {
        "summary": summary,
        "daily": aggregate_daily_counts(chat_prompts, codex_prompts, matches),
        "repo": aggregate_repo_counts(chat_prompts, codex_prompts, matches),
        "conversation": aggregate_conversation_counts(chat_prompts, matches),
        "rollout": aggregate_rollout_counts(codex_prompts, matches),
        "chat_prompts": drop_internal(chat_prompts),
        "codex_prompts": drop_internal(codex_prompts),
        "matches": drop_internal(matches),
        "unmatched_chat": drop_internal(unmatched_chat),
        "unmatched_codex": drop_internal(unmatched_codex),
        "meta": {
            "codex_sessions_root": str(codex_sessions_root),
            "rollout_file_count": len(rollout_paths),
        },
    }


def collect_stats_from_inputs(paths: Iterable[Path], marker: Optional[str], local_tz, rules: dict) -> dict:
    estimate_tokens, token_estimation_method = build_token_estimator()

    monthly_user: Counter[str] = Counter()
    monthly_conv_ids: Dict[str, set[str]] = defaultdict(set)
    monthly_active_days: Dict[str, set[str]] = defaultdict(set)
    daily_user: Counter[str] = Counter()
    daily_conv_ids: Dict[str, set[str]] = defaultdict(set)
    daily_hourly: Counter[tuple[str, int]] = Counter()
    monthly_weekday_hour: Counter[tuple[str, int, int]] = Counter()
    daily_conv_user_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    monthly_role_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    monthly_role_tokens: Dict[str, Counter[str]] = defaultdict(Counter)
    conv_titles: Dict[str, str] = {}
    conversation_stats: Dict[str, dict] = {}
    monthly_keyword_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    monthly_daily_user_counts: Dict[str, Counter[int]] = defaultdict(Counter)
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
                token_est = estimate_tokens(text)
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
                monthly_role_tokens[month][role] += int(token_est)
                if role == "user":
                    monthly_user[month] += 1
                    monthly_conv_ids[month].add(conv_id)
                    monthly_active_days[month].add(day)
                    monthly_daily_user_counts[month][dt.day] += 1
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
    latest_month = max(months) if months else None
    for month in months:
        role_counts = monthly_role_counts.get(month, Counter())
        role_token_counts = monthly_role_tokens.get(month, Counter())
        user_count = int(monthly_user.get(month, 0))
        active_days_count = int(len(monthly_active_days.get(month, set())))
        total_days = month_total_days(month)
        last_data_day = max(monthly_daily_user_counts.get(month, Counter()).keys(), default=0)
        is_in_progress = month == latest_month and 0 < last_data_day < total_days
        elapsed_days = last_data_day if is_in_progress else total_days
        elapsed_days = elapsed_days if elapsed_days > 0 else total_days
        daily_series = [
            int(monthly_daily_user_counts.get(month, Counter()).get(day, 0))
            for day in range(1, elapsed_days + 1)
        ]
        avg_per_elapsed_day = float(user_count / elapsed_days) if elapsed_days else 0.0
        avg_per_active_day = float(user_count / active_days_count) if active_days_count else 0.0
        median_daily_user_messages = median_value(daily_series)
        day_counter = monthly_daily_user_counts.get(month, Counter())
        if day_counter:
            peak_day, peak_count = min(day_counter.items(), key=lambda kv: (-kv[1], kv[0]))
            peak_daily_user_messages = int(peak_count)
            peak_daily_date = f"{month}-{peak_day:02d}"
        else:
            peak_daily_user_messages = 0
            peak_daily_date = ""
        user_tokens_est = int(role_token_counts.get("user", 0))
        assistant_tokens_est = int(role_token_counts.get("assistant", 0))
        system_tokens_est = int(role_token_counts.get("system", 0))
        tool_tokens_est = int(role_token_counts.get("tool", 0))
        other_tokens_est = int(role_token_counts.get("other", 0))
        total_tokens_est = (
            user_tokens_est
            + assistant_tokens_est
            + system_tokens_est
            + tool_tokens_est
            + other_tokens_est
        )
        avg_user_tokens_est = float(user_tokens_est / user_count) if user_count else 0.0
        avg_tokens_per_active_day_est = (
            float(total_tokens_est / active_days_count) if active_days_count else 0.0
        )
        monthly_rows.append(
            {
                "month": month,
                "year": month[:4],
                "user_messages": user_count,
                "assistant_messages": int(role_counts.get("assistant", 0)),
                "system_messages": int(role_counts.get("system", 0)),
                "tool_messages": int(role_counts.get("tool", 0)),
                "other_messages": int(role_counts.get("other", 0)),
                "total_messages": int(sum(role_counts.values())),
                "conversations": int(len(monthly_conv_ids.get(month, set()))),
                "active_days": active_days_count,
                "user_tokens_est": user_tokens_est,
                "assistant_tokens_est": assistant_tokens_est,
                "system_tokens_est": system_tokens_est,
                "tool_tokens_est": tool_tokens_est,
                "other_tokens_est": other_tokens_est,
                "total_tokens_est": total_tokens_est,
                "avg_user_tokens_est": avg_user_tokens_est,
                "avg_tokens_per_active_day_est": avg_tokens_per_active_day_est,
                "avg_per_elapsed_day": avg_per_elapsed_day,
                "avg_per_active_day": avg_per_active_day,
                "median_daily_user_messages": median_daily_user_messages,
                "peak_daily_user_messages": peak_daily_user_messages,
                "peak_daily_date": peak_daily_date,
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
                "token_estimation": "local estimate from message body text only (not API billing tokens)",
            },
            "stats": {
                "total_conversation_objects": total_conversation_objects,
                "total_unique_messages": total_unique_messages,
                "total_duplicate_messages_skipped": total_duplicate_messages_skipped,
                "total_timestamped_messages": total_timestamped_messages,
                "total_conversations": len(conversation_index),
                "token_estimation_method": token_estimation_method,
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
        "## Definitions",
        "- user_messages: `author.role == user`",
        "- conversations: unique conversation_id with >=1 user message in period",
        "- active_days: unique local dates with >=1 user message in period",
        "- timestamp: `create_time` first, fallback to `update_time`",
        "",
        "## Monthly",
    ]
    if not monthly:
        lines.append("- no data")
    else:
        for row in monthly:
            lines.append(
                f"- `{row['month']}`: user={row['user_messages']} / conversations={row['conversations']} / active_days={row['active_days']}"
            )
    lines.extend(
        [
            "",
            "## Metadata",
            f"- timezone: `{parsed['meta'].get('timezone', 'unknown')}`",
            f"- generated_at: `{parsed['meta'].get('generated_at', 'unknown')}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_codex_match_outputs(output_dir: Path, codex_match: Optional[dict]) -> None:
    out_dir = output_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "codex_chat_match_2026-04_summary.md"
    chat_csv = out_dir / "codex_chat_match_2026-04_chat_prompts.csv"
    codex_csv = out_dir / "codex_chat_match_2026-04_codex_prompts.csv"
    matches_csv = out_dir / "codex_chat_match_2026-04_matches.csv"
    unmatched_chat_csv = out_dir / "codex_chat_match_2026-04_unmatched_chat.csv"
    unmatched_codex_csv = out_dir / "codex_chat_match_2026-04_unmatched_codex.csv"

    if not codex_match:
        write_csv(chat_csv, ["chat_prompt_id"], [])
        write_csv(codex_csv, ["codex_prompt_id"], [])
        write_csv(matches_csv, ["match_id"], [])
        write_csv(unmatched_chat_csv, ["chat_prompt_id"], [])
        write_csv(unmatched_codex_csv, ["codex_prompt_id"], [])
        summary_path.write_text("# Codex遯∝粋繧ｵ繝槭Μ繝ｼ\n\n繝・・繧ｿ縺後≠繧翫∪縺帙ｓ縲・n", encoding="utf-8")
        return

    summary = codex_match.get("summary", {})
    chat_prompts = codex_match.get("chat_prompts", [])
    codex_prompts = codex_match.get("codex_prompts", [])
    matches = codex_match.get("matches", [])
    unmatched_chat = codex_match.get("unmatched_chat", [])
    unmatched_codex = codex_match.get("unmatched_codex", [])

    write_csv(
        chat_csv,
        [
            "chat_prompt_id",
            "date_jst",
            "conversation_id",
            "conversation_title",
            "message_id",
            "prompt_hash",
            "normalized_hash",
            "snippet",
            "estimated_repo",
            "confidence",
        ],
        [
            [
                row.get("chat_prompt_id", ""),
                row.get("date_jst", ""),
                row.get("conversation_id", ""),
                row.get("conversation_title", ""),
                row.get("message_id", ""),
                row.get("prompt_hash", ""),
                row.get("normalized_hash", ""),
                row.get("snippet", ""),
                row.get("estimated_repo", ""),
                row.get("confidence", ""),
            ]
            for row in chat_prompts
        ],
    )

    write_csv(
        codex_csv,
        [
            "codex_prompt_id",
            "date_jst",
            "rollout_path",
            "session_id",
            "event_index",
            "prompt_hash",
            "normalized_hash",
            "snippet",
            "cwd_or_repo",
            "confidence",
        ],
        [
            [
                row.get("codex_prompt_id", ""),
                row.get("date_jst", ""),
                row.get("rollout_path", ""),
                row.get("session_id", ""),
                row.get("event_index", ""),
                row.get("prompt_hash", ""),
                row.get("normalized_hash", ""),
                row.get("snippet", ""),
                row.get("cwd_or_repo", ""),
                row.get("confidence", ""),
            ]
            for row in codex_prompts
        ],
    )

    write_csv(
        matches_csv,
        [
            "match_id",
            "match_type",
            "confidence",
            "similarity",
            "chat_prompt_id",
            "codex_prompt_id",
            "date_jst",
            "conversation_title",
            "rollout_path",
            "estimated_repo",
            "cwd_or_repo",
            "snippet",
        ],
        [
            [
                row.get("match_id", ""),
                row.get("match_type", ""),
                row.get("confidence", ""),
                row.get("similarity", ""),
                row.get("chat_prompt_id", ""),
                row.get("codex_prompt_id", ""),
                row.get("date_jst", ""),
                row.get("conversation_title", ""),
                row.get("rollout_path", ""),
                row.get("estimated_repo", ""),
                row.get("cwd_or_repo", ""),
                row.get("snippet", ""),
            ]
            for row in matches
        ],
    )

    write_csv(
        unmatched_chat_csv,
        [
            "chat_prompt_id",
            "date_jst",
            "conversation_title",
            "estimated_repo",
            "snippet",
        ],
        [
            [
                row.get("chat_prompt_id", ""),
                row.get("date_jst", ""),
                row.get("conversation_title", ""),
                row.get("estimated_repo", ""),
                row.get("snippet", ""),
            ]
            for row in unmatched_chat
        ],
    )

    write_csv(
        unmatched_codex_csv,
        [
            "codex_prompt_id",
            "date_jst",
            "rollout_path",
            "cwd_or_repo",
            "snippet",
        ],
        [
            [
                row.get("codex_prompt_id", ""),
                row.get("date_jst", ""),
                row.get("rollout_path", ""),
                row.get("cwd_or_repo", ""),
                row.get("snippet", ""),
            ]
            for row in unmatched_codex
        ],
    )

    lines = [
        "# 2026-04 Codex Match Summary",
        "",
        f"- Range (JST): {summary.get('range_start_jst', '')} ~ {summary.get('range_end_jst', '')}",
        f"- chat_codex_prompt_count: {summary.get('chat_codex_prompt_count', 0)}",
        f"- codex_user_prompt_count: {summary.get('codex_user_prompt_count', 0)}",
        f"- matched_prompt_count: {summary.get('matched_prompt_count', 0)}",
        f"- chat_only_prompt_count: {summary.get('chat_only_prompt_count', 0)}",
        f"- codex_only_prompt_count: {summary.get('codex_only_prompt_count', 0)}",
        f"- exact_match_count: {summary.get('exact_match_count', 0)}",
        f"- near_match_count: {summary.get('near_match_count', 0)}",
        "",
        "## 注意",
        "- ChatGPT側の数は「ChatGPT内で生成されたCodex向け完成プロンプト数」。",
        "- Codex側の数は「Codexローカルログに残っているuser_message数」。",
        "- matchedは「正規化後に一致または高類似と判定されたもの」。",
        "- chat_onlyは「作ったが投げていない可能性、または編集して投げたため一致しなかった可能性」。",
        "- codex_onlyは「ChatGPTを経由せずCodexへ直接入力した可能性、またはChatGPT側抽出に失敗した可能性」。",
        "- これはOpenAIの課金トークンや公式利用回数ではなく、ローカルログ解析による実用集計。",
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def _json_for_file(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(_json_for_file(data), encoding="utf-8")


def build_dashboard_summary_payload(parsed: dict) -> dict:
    meta = parsed.get("meta", {})
    return {
        "meta": {
            "generated_at": meta.get("generated_at", ""),
            "timezone": meta.get("timezone", ""),
            "stats": meta.get("stats", {}),
        },
        "monthly": sorted(parsed.get("monthly", []), key=lambda r: r["month"]),
    }


def build_dashboard_conversations_payload(parsed: dict) -> dict:
    rows = sorted(
        parsed.get("conversation_index", []),
        key=lambda row: (
            row.get("last_message_at") or "",
            row.get("total_message_count", 0),
            row.get("conversation_id", ""),
        ),
        reverse=True,
    )
    meta = parsed.get("meta", {})
    return {
        "meta": {
            "generated_at": meta.get("generated_at", ""),
            "timezone": meta.get("timezone", ""),
        },
        "total": len(rows),
        "items": rows,
    }


def build_dashboard_daily_payload(parsed: dict) -> dict:
    meta = parsed.get("meta", {})
    return {
        "meta": {
            "generated_at": meta.get("generated_at", ""),
            "timezone": meta.get("timezone", ""),
        },
        "daily": sorted(parsed.get("daily", []), key=lambda r: r["date"]),
        "daily_hourly": sorted(parsed.get("daily_hourly", []), key=lambda r: (r["date"], r["hour"])),
        "monthly_weekday_hour": sorted(
            parsed.get("monthly_weekday_hour", []), key=lambda r: (r["month"], r["weekday"], r["hour"])
        ),
        "daily_top_conversations": sorted(
            parsed.get("daily_top_conversations", []), key=lambda r: (r["date"], r["rank"])
        ),
    }


def build_dashboard_categories_payload(parsed: dict) -> dict:
    meta = parsed.get("meta", {})
    return {
        "meta": {
            "generated_at": meta.get("generated_at", ""),
            "timezone": meta.get("timezone", ""),
        },
        "category_monthly": sorted(parsed.get("category_monthly", []), key=lambda r: (r["month"], r["category"])),
        "category_daily": sorted(parsed.get("category_daily", []), key=lambda r: (r["date"], r["category"])),
        "keywords_monthly": sorted(
            parsed.get("keywords_monthly", []), key=lambda r: (r["month"], -r["count"], r["keyword"])
        ),
        "role_monthly": sorted(parsed.get("role_monthly", []), key=lambda r: r["month"]),
    }


def build_dashboard_codex_payload(parsed: dict) -> dict:
    codex_match = parsed.get("codex_match")
    return codex_match if isinstance(codex_match, dict) else {}


def build_dashboard_html() -> str:
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChatGPT / Codex 活動ダッシュボード</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --card: #ffffff;
      --line: #d8e0ea;
      --ink: #1d2733;
      --muted: #5d6b7c;
      --primary: #1b67d6;
      --soft: #e9f1ff;
      --warn: #fff2e8;
      --error: #fde8e8;
      --radius: 14px;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: radial-gradient(circle at top left, #eef4ff 0, #f4f7fb 42%, #eef3f8 100%); color: var(--ink); font-family: "Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif; line-height: 1.5; }
    .wrap { max-width: 1280px; margin: 0 auto; padding: 20px 16px 40px; display: grid; gap: 16px; }
    .panel { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; box-shadow: 0 4px 18px rgba(25,45,65,0.06); }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 1.5rem; }
    h2 { font-size: 1.08rem; margin-bottom: 8px; }
    h3 { font-size: 0.98rem; margin-top: 12px; }
    .sub { color: var(--muted); margin-top: 4px; font-size: 0.92rem; }
    .meta, .status-line { color: var(--muted); font-size: 0.85rem; display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
    .toolbar { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    button {
      border: 1px solid var(--primary);
      background: var(--primary);
      color: white;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 0.9rem;
      cursor: pointer;
    }
    button.secondary { background: #fff; color: var(--primary); }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }
    .card { border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: linear-gradient(180deg, #fff, #f9fcff); }
    .card.emph { background: linear-gradient(180deg, #fff, var(--soft)); }
    .label { font-size: 0.78rem; color: var(--muted); }
    .value { margin-top: 4px; font-size: 1.15rem; font-weight: 700; }
    .unit { font-size: 0.76rem; color: var(--muted); }
    .muted { color: var(--muted); }
    .note { margin-top: 8px; border-left: 4px solid #f2b07d; background: var(--warn); padding: 8px 10px; border-radius: 8px; font-size: 0.86rem; color: #7c4a21; }
    .error { margin-top: 8px; border-left: 4px solid #c53030; background: var(--error); padding: 8px 10px; border-radius: 8px; color: #8b1d1d; }
    .list { display: grid; gap: 10px; }
    .row { border: 1px solid var(--line); border-radius: 12px; padding: 10px; background: #fff; }
    .row-grid { display: grid; grid-template-columns: 120px 1fr repeat(4, minmax(90px, 120px)); gap: 8px; align-items: start; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.35; }
    .chip { display: inline-block; border-radius: 999px; border: 1px solid #bdd1f5; background: var(--soft); color: #1d4fa6; padding: 2px 8px; font-size: 0.75rem; white-space: nowrap; }
    .kv { display: flex; justify-content: space-between; gap: 10px; font-size: 0.86rem; border-bottom: 1px dotted var(--line); padding: 3px 0; }
    .kv:last-child { border-bottom: 0; }
    .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-top: 8px; margin-bottom: 6px; }
    label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 4px; }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      font-size: 0.9rem;
      color: var(--ink);
    }
    .empty { color: var(--muted); font-size: 0.9rem; padding: 8px 0; }
    .range { font-size: 0.86rem; color: var(--muted); margin-top: 6px; }
    .section-body[aria-busy="true"] { opacity: 0.7; }
    .more-wrap { display: flex; justify-content: center; padding-top: 4px; }
    .more-wrap button { min-width: 180px; }
    .codex-list .row-grid { grid-template-columns: 110px 90px 80px 1fr; }
    .snippet { word-break: break-word; color: #334155; }
    details { margin-top: 8px; border-top: 1px dashed var(--line); padding-top: 8px; }
    details > summary { cursor: pointer; color: var(--primary); font-size: 0.86rem; font-weight: 600; }
    .mono { font-variant-numeric: tabular-nums; }
    @media (max-width: 960px) {
      .row-grid { grid-template-columns: 1fr 1fr; }
      .num { text-align: left; }
      .codex-list .row-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <div class="toolbar">
        <div>
          <h1>ChatGPT / Codex 活動ダッシュボード</h1>
          <div class="sub">最初に読むのはサマリーだけ。詳細はボタンで段階的に読み込みます。</div>
        </div>
        <div class="actions">
          <span class="chip" id="summaryPhase">読み込み待ち</span>
        </div>
      </div>
      <div class="meta" id="metaInfo"></div>
      <div class="status-line" id="summaryStatus">読み込み中...</div>
    </section>

    <section class="panel">
      <h2>全体サマリー</h2>
      <div class="cards" id="summaryCards"></div>
      <div class="note">推定トークンはローカルで概算した値です。OpenAIの課金トークンや公式利用量ではありません。</div>
    </section>

    <section class="panel">
      <h2>月別サマリー</h2>
      <div class="list" id="monthlyList"></div>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div>
          <h2>会話一覧</h2>
          <div class="sub">会話一覧用の別JSONを、必要になった時だけ読み込みます。ページング表示です。</div>
        </div>
        <div class="actions">
          <button type="button" id="loadConversationsBtn">会話一覧を読み込む（ページング表示）</button>
          <span class="chip" id="conversationState">未読み込み</span>
        </div>
      </div>
      <div class="filters">
        <div>
          <label for="titleSearch">タイトル・キーワード検索</label>
          <input id="titleSearch" type="text" placeholder="読み込み後に使えます" disabled />
        </div>
        <div>
          <label for="monthFilter">年月フィルタ</label>
          <select id="monthFilter" disabled>
            <option value="all">読み込み後に選択</option>
          </select>
        </div>
        <div>
          <label for="categoryFilter">カテゴリフィルタ</label>
          <select id="categoryFilter" disabled>
            <option value="all">読み込み後に選択</option>
          </select>
        </div>
        <div>
          <label for="sortBy">表示順</label>
          <select id="sortBy" disabled>
            <option value="messages_desc">合計メッセージが多い順</option>
            <option value="last_desc">終了が新しい順</option>
          </select>
        </div>
      </div>
      <div class="range" id="conversationCount">未読み込み</div>
      <div class="status-line" id="conversationStatus"></div>
      <div class="list" id="conversationList"></div>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div>
          <h2>日別詳細</h2>
          <div class="sub">日別・時間帯別の詳細は、必要なときだけ読み込みます。</div>
        </div>
        <div class="actions">
          <button type="button" id="loadDailyBtn">日別詳細を読み込む（時間帯・上位会話を含む）</button>
          <span class="chip" id="dailyState">未読み込み</span>
        </div>
      </div>
      <div class="filters">
        <div>
          <label for="daySelect">日付</label>
          <select id="daySelect" disabled>
            <option value="">読み込み後に選択</option>
          </select>
        </div>
      </div>
      <div class="status-line" id="dailyStatus"></div>
      <div class="list" id="dailyList"></div>
      <details id="dailyHourlyDetails" hidden>
        <summary>時間帯別の詳細</summary>
        <div class="list" id="dailyHourlyList" style="margin-top:8px;"></div>
      </details>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div>
          <h2>カテゴリ・キーワード詳細</h2>
          <div class="sub">カテゴリやキーワードの別JSONを、必要なときだけ読み込みます。</div>
        </div>
        <div class="actions">
          <button type="button" id="loadCategoriesBtn">カテゴリ詳細を読み込む</button>
          <span class="chip" id="categoriesState">未読み込み</span>
        </div>
      </div>
      <div class="status-line" id="categoriesStatus"></div>
      <div class="list" id="categoryMonthlyList"></div>
      <h3>カテゴリの日別詳細</h3>
      <div class="list" id="categoryDailyList"></div>
      <h3>月別キーワード</h3>
      <div class="list" id="keywordsMonthlyList"></div>
    </section>

    <section class="panel">
      <div class="toolbar">
        <div>
          <h2>Codex照合詳細</h2>
          <div class="sub">照合結果は初期表示に含めず、必要時のみ読み込みます。</div>
        </div>
        <div class="actions">
          <button type="button" id="loadCodexBtn">Codex照合を読み込む（詳細は後から表示）</button>
          <span class="chip" id="codexState">未読み込み</span>
        </div>
      </div>
      <div class="status-line" id="codexStatus"></div>
      <div class="cards" id="codexSummaryCards"></div>
      <h3>一致一覧</h3>
      <div class="list codex-list" id="codexMatchedList"></div>
      <h3>ChatGPT側だけにあるもの</h3>
      <div class="list codex-list" id="codexChatOnlyList"></div>
      <h3>Codex側だけにあるもの</h3>
      <div class="list codex-list" id="codexOnlyList"></div>
    </section>
  </div>

  <script>
    const FILES = {
      summary: "dashboard_summary.json",
      conversations: "dashboard_conversations.json",
      daily: "dashboard_daily.json",
      categories: "dashboard_categories.json",
      codex: "dashboard_codex_match.json",
    };
    const state = {
      summary: null,
      conversations: null,
      daily: null,
      categories: null,
      codex: null,
      conversationFilters: {
        titleSearch: "",
        monthFilter: "all",
        categoryFilter: "all",
        sortBy: "messages_desc",
      },
      conversationVisibleCount: 50,
      conversationLoading: false,
      conversationLoaded: false,
      dailySelected: "",
      dailyLoading: false,
      dailyLoaded: false,
      categoriesLoading: false,
      categoriesLoaded: false,
      codexLoading: false,
      codexLoaded: false,
      codexVisibleCounts: {
        matched: 30,
        chatOnly: 30,
        codexOnly: 30,
      },
    };

    const fmtInt = (v) => Number(v || 0).toLocaleString("ja-JP");
    const fmtDec = (v) => Number(v || 0).toLocaleString("ja-JP", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const escapeHtml = (value) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    const monthToJp = (month) => {
      if (!month || !/^\\d{4}-\\d{2}$/.test(month)) return month || "-";
      return `${month.slice(0, 4)}年${month.slice(5, 7)}月`;
    };
    const monthOfIso = (iso) => (iso && iso.length >= 7 ? iso.slice(0, 7) : "");

    function parseIso(iso) {
      if (!iso) return null;
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? null : d;
    }

    function fmtDateShort(dateText) {
      const d = parseIso(dateText);
      if (!d) return dateText || "-";
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const day = String(d.getDate()).padStart(2, "0");
      const h = String(d.getHours()).padStart(2, "0");
      const min = String(d.getMinutes()).padStart(2, "0");
      return `${y}/${m}/${day} ${h}:${min}`;
    }

    function fmtPeriod(firstIso, lastIso) {
      const start = fmtDateShort(firstIso);
      const end = fmtDateShort(lastIso);
      if (start.slice(0, 10) === end.slice(0, 10)) {
        return `${start} → ${end.slice(11)}`;
      }
      return `${start} → ${end}`;
    }

    function setStatus(id, message, kind = "info") {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = kind === "error" ? "error" : "status-line";
      el.textContent = message;
    }

    function setChip(id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    }

    async function fetchJson(path) {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`${path} の取得に失敗しました (${response.status})`);
      }
      return response.json();
    }

    function renderMeta(summary) {
      const stats = summary?.meta?.stats || {};
      const metaInfo = [
        `生成時刻: ${summary?.meta?.generated_at || "-"}`,
        `タイムゾーン: ${summary?.meta?.timezone || "-"}`,
        `入力会話オブジェクト: ${fmtInt(stats.total_conversation_objects || 0)}`,
        `ユニークメッセージ: ${fmtInt(stats.total_unique_messages || 0)}`,
        `重複スキップ: ${fmtInt(stats.total_duplicate_messages_skipped || 0)}`,
      ];
      document.getElementById("metaInfo").innerHTML = metaInfo.map((text) => `<span>${escapeHtml(text)}</span>`).join("");
      setChip("summaryPhase", "サマリー表示中");
    }

    function renderSummaryCards(summary) {
      const stats = summary?.meta?.stats || {};
      const monthly = summary?.monthly || [];
      const totalUser = monthly.reduce((acc, row) => acc + Number(row.user_messages || 0), 0);
      const totalAssistant = monthly.reduce((acc, row) => acc + Number(row.assistant_messages || 0), 0);
      const totalTokens = monthly.reduce((acc, row) => acc + Number(row.total_tokens_est || 0), 0);
      const activeDays = monthly.reduce((acc, row) => acc + Number(row.active_days || 0), 0);
      const peakMonth = monthly.length
        ? monthly.reduce((best, row) => (Number(row.user_messages || 0) > Number(best.user_messages || 0) ? row : best), monthly[0])
        : null;
      const cards = [
        ["総メッセージ数", fmtInt(stats.total_unique_messages || 0), ""],
        ["あなたの発言数", fmtInt(totalUser), ""],
        ["AI返答数", fmtInt(totalAssistant), ""],
        ["会話スレッド数", fmtInt(stats.total_conversations || 0), ""],
        ["活動日数", fmtInt(activeDays), "日"],
        ["推定総トークン", fmtInt(totalTokens), "tok"],
        ["一番多かった月", peakMonth ? `${monthToJp(peakMonth.month)} (${fmtInt(peakMonth.user_messages)})` : "-", ""],
      ];
      document.getElementById("summaryCards").innerHTML = cards
        .map(([label, value, unit]) => `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div>${unit ? `<div class="unit">${escapeHtml(unit)}</div>` : ""}</div>`)
        .join("");
    }

    function renderMonthlyList(summary) {
      const monthly = (summary?.monthly || []).slice().sort((a, b) => b.month.localeCompare(a.month));
      const root = document.getElementById("monthlyList");
      if (!monthly.length) {
        root.innerHTML = `<div class="empty">月別データがありません。</div>`;
        return;
      }
      root.innerHTML = monthly.map((row) => `
        <article class="row">
          <div class="row-grid">
            <div><span class="chip">${escapeHtml(monthToJp(row.month))}</span></div>
            <div></div>
            <div class="num"><div class="label">会話スレッド数</div><div>${fmtInt(row.conversations)}</div></div>
            <div class="num"><div class="label">あなたの発言数</div><div>${fmtInt(row.user_messages)}</div></div>
            <div class="num"><div class="label">推定総トークン</div><div>${fmtInt(row.total_tokens_est)} tok</div></div>
            <div class="num"><div class="label">活動日数</div><div>${fmtInt(row.active_days)} 日</div></div>
            <div class="num"><div class="label">最大日の発言数</div><div>${fmtInt(row.peak_daily_user_messages)}</div></div>
          </div>
          <details>
            <summary>詳細</summary>
            <div class="kv"><span>あなたの入力トークン</span><strong>${fmtInt(row.user_tokens_est)} tok</strong></div>
            <div class="kv"><span>AI返答トークン</span><strong>${fmtInt(row.assistant_tokens_est)} tok</strong></div>
            <div class="kv"><span>1発言あたり入力トークン</span><strong>${fmtDec(row.avg_user_tokens_est)}</strong></div>
            <div class="kv"><span>1日あたり推定トークン</span><strong>${fmtDec(row.avg_tokens_per_active_day_est)}</strong></div>
            <div class="kv"><span>最大日の日付</span><strong>${escapeHtml((row.peak_daily_date || "").replaceAll("-", "/"))}</strong></div>
          </details>
        </article>
      `).join("");
    }

    function setConversationControlsEnabled(enabled) {
      for (const id of ["titleSearch", "monthFilter", "categoryFilter", "sortBy"]) {
        document.getElementById(id).disabled = !enabled;
      }
    }

    function availableConversationRows() {
      const rows = (state.conversations?.items || []).slice();
      const q = state.conversationFilters.titleSearch.trim().toLowerCase();
      let filtered = rows;
      if (q) {
        filtered = filtered.filter((row) => {
          const title = String(row.title || "").toLowerCase();
          const keywords = (Array.isArray(row.top_keywords) ? row.top_keywords : []).join(" ").toLowerCase();
          return title.includes(q) || keywords.includes(q);
        });
      }
      if (state.conversationFilters.monthFilter !== "all") {
        filtered = filtered.filter((row) => monthOfIso(row.last_message_at) === state.conversationFilters.monthFilter);
      }
      if (state.conversationFilters.categoryFilter !== "all") {
        filtered = filtered.filter((row) => (row.inferred_category || "その他") === state.conversationFilters.categoryFilter);
      }
      filtered.sort((a, b) => {
        if (state.conversationFilters.sortBy === "last_desc") {
          return String(b.last_message_at || "").localeCompare(String(a.last_message_at || ""));
        }
        const totalDiff = Number(b.total_message_count || 0) - Number(a.total_message_count || 0);
        if (totalDiff !== 0) return totalDiff;
        return String(b.last_message_at || "").localeCompare(String(a.last_message_at || ""));
      });
      return filtered;
    }

    function renderConversationFilters(rows) {
      const months = Array.from(new Set(rows.map((row) => monthOfIso(row.last_message_at)).filter(Boolean))).sort();
      const categories = Array.from(new Set(rows.map((row) => row.inferred_category || "その他"))).sort();
      const monthFilter = document.getElementById("monthFilter");
      const categoryFilter = document.getElementById("categoryFilter");
      monthFilter.innerHTML = `<option value="all">すべて</option>` + months.map((m) => `<option value="${m}">${monthToJp(m)}</option>`).join("");
      categoryFilter.innerHTML = `<option value="all">すべて</option>` + categories.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
      monthFilter.value = state.conversationFilters.monthFilter;
      categoryFilter.value = state.conversationFilters.categoryFilter;
      document.getElementById("sortBy").value = state.conversationFilters.sortBy;
    }

    function renderConversationList() {
      const root = document.getElementById("conversationList");
      const count = document.getElementById("conversationCount");
      if (!state.conversationLoaded) {
        root.innerHTML = `<div class="empty">会話一覧はまだ読み込まれていません。</div>`;
        count.textContent = "未読み込み";
        return;
      }
      const rows = availableConversationRows();
      const visible = rows.slice(0, state.conversationVisibleCount);
      count.textContent = `表示中: 1-${Math.min(visible.length, rows.length)} / 全${fmtInt(rows.length)}件`;
      if (!rows.length) {
        root.innerHTML = `<div class="empty">条件に一致する会話スレッドがありません。</div>`;
        return;
      }
      const more = rows.length > visible.length;
      root.innerHTML = `
        ${visible.map((row) => {
          const keywords = Array.isArray(row.top_keywords) ? row.top_keywords : [];
          return `
            <article class="row">
              <div class="row-grid">
                <div>
                  <div class="label">タイトル</div>
                  <div class="title" title="${escapeHtml(row.title || "")}">${escapeHtml(row.title || "(untitled)")}</div>
                </div>
                <div>
                  <div class="label">分類</div>
                  <div><span class="chip">${escapeHtml(row.inferred_category || "その他")}</span></div>
                </div>
                <div class="num"><div class="label">あなたの発言</div><div>${fmtInt(row.user_message_count)}</div></div>
                <div class="num"><div class="label">AI返答</div><div>${fmtInt(row.assistant_message_count)}</div></div>
                <div class="num"><div class="label">合計</div><div>${fmtInt(row.total_message_count)}</div></div>
                <div>
                  <div class="label">期間</div>
                  <div class="mono">${escapeHtml(fmtPeriod(row.first_message_at, row.last_message_at))}</div>
                </div>
              </div>
              <div style="margin-top:6px;"><span class="label">キーワード:</span> <span class="snippet">${escapeHtml(keywords.join(", "))}</span></div>
            </article>
          `;
        }).join("")}
        ${more ? `<div class="more-wrap"><button type="button" id="conversationMoreBtn">さらに表示</button></div>` : ""}
      `;
      const moreBtn = document.getElementById("conversationMoreBtn");
      if (moreBtn) {
        moreBtn.addEventListener("click", () => {
          state.conversationVisibleCount += 50;
          renderConversationList();
        });
      }
    }

    function renderConversationSection() {
      const rows = (state.conversations?.items || []).slice();
      if (!rows.length) return;
      renderConversationFilters(rows);
      renderConversationList();
      setConversationControlsEnabled(true);
      setChip("conversationState", "読み込み済み");
      setStatus("conversationStatus", `読み込み完了: ${fmtInt(rows.length)}件`);
    }

    function loadConversationSection() {
      if (state.conversationLoading || state.conversationLoaded) return;
      state.conversationLoading = true;
      setChip("conversationState", "読み込み中");
      setStatus("conversationStatus", "会話一覧JSONを読み込んでいます...");
      fetchJson(FILES.conversations)
        .then((data) => {
          state.conversations = data;
          state.conversationLoaded = true;
          state.conversationVisibleCount = 50;
          state.conversationLoading = false;
          renderConversationSection();
        })
        .catch((error) => {
          state.conversationLoading = false;
          setChip("conversationState", "読み込み失敗");
          setStatus(
            "conversationStatus",
            `会話一覧の読み込みに失敗しました。ローカルHTTPサーバーで開いているか確認してください。${error.message}`,
            "error",
          );
        });
    }

    function renderDailyList() {
      const root = document.getElementById("dailyList");
      if (!state.dailyLoaded) {
        root.innerHTML = `<div class="empty">日別詳細はまだ読み込まれていません。</div>`;
        return;
      }
      const rows = (state.daily?.daily || []).slice();
      root.innerHTML = rows.map((row) => `
        <article class="row">
          <div class="row-grid">
            <div><span class="chip">${escapeHtml(row.date.replaceAll("-", "/"))}</span></div>
            <div></div>
            <div class="num"><div class="label">あなたの発言数</div><div>${fmtInt(row.user_messages)}</div></div>
            <div class="num"><div class="label">会話数</div><div>${fmtInt(row.conversations)}</div></div>
            <div></div>
            <div><span class="chip">${escapeHtml(monthToJp(row.month))}</span></div>
          </div>
        </article>
      `).join("");
    }

    function renderDailyTopForSelectedDay() {
      const root = document.getElementById("dailyHourlyList");
      const details = document.getElementById("dailyHourlyDetails");
      if (!state.dailyLoaded || !state.dailySelected) {
        root.innerHTML = `<div class="empty">日付を選択してください。</div>`;
        details.hidden = true;
        return;
      }
      const dailyRows = (state.daily?.daily_top_conversations || []).filter((row) => row.date === state.dailySelected).sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
      const hourlyRows = (state.daily?.daily_hourly || []).filter((row) => row.date === state.dailySelected).sort((a, b) => Number(a.hour || 0) - Number(b.hour || 0));
      const dayRows = dailyRows.map((row) => `
        <article class="row">
          <div class="row-grid" style="grid-template-columns: 60px 1fr 120px 120px;">
            <div><span class="chip">#${fmtInt(row.rank)}</span></div>
            <div class="title" title="${escapeHtml(row.title || "")}">${escapeHtml(row.title || "(untitled)")}</div>
            <div class="num"><div class="label">あなたの発言</div><div>${fmtInt(row.user_messages)}</div></div>
            <div><span class="chip">${escapeHtml(row.inferred_category || "その他")}</span></div>
          </div>
        </article>
      `).join("");
      root.innerHTML = `
        <div class="range">選択日: ${escapeHtml(state.dailySelected.replaceAll("-", "/"))}</div>
        ${dayRows || `<div class="empty">この日の上位スレッドはありません。</div>`}
        <div class="note">時間帯別の詳細は下の折りたたみを開くと見られます。</div>
      `;
      details.hidden = false;
      details.open = true;
      const hourly = hourlyRows.length
        ? hourlyRows.map((row) => `<div class="kv"><span>${String(row.hour).padStart(2, "0")}:00</span><strong>${fmtInt(row.user_messages)} 件</strong></div>`).join("")
        : `<div class="empty">この日の時間帯データはありません。</div>`;
      document.getElementById("dailyHourlyList").innerHTML = hourly;
    }

    function renderDailyControls(rows) {
      const select = document.getElementById("daySelect");
      select.innerHTML = rows.map((row) => `<option value="${row.date}">${row.date.replaceAll("-", "/")}</option>`).join("");
      state.dailySelected = state.dailySelected || rows[rows.length - 1]?.date || "";
      select.value = state.dailySelected;
      select.disabled = false;
    }

    function loadDailySection() {
      if (state.dailyLoading || state.dailyLoaded) return;
      state.dailyLoading = true;
      setChip("dailyState", "読み込み中");
      setStatus("dailyStatus", "日別詳細JSONを読み込んでいます...");
      fetchJson(FILES.daily)
        .then((data) => {
          state.daily = data;
          state.dailyLoaded = true;
          state.dailyLoading = false;
          const rows = (state.daily?.daily || []).slice();
          renderDailyControls(rows);
          renderDailyList();
          renderDailyTopForSelectedDay();
          setChip("dailyState", "読み込み済み");
          setStatus("dailyStatus", `読み込み完了: ${fmtInt(rows.length)}日分`);
        })
        .catch((error) => {
          state.dailyLoading = false;
          setChip("dailyState", "読み込み失敗");
          setStatus(
            "dailyStatus",
            `日別詳細の読み込みに失敗しました。ローカルHTTPサーバーで開いているか確認してください。${error.message}`,
            "error",
          );
        });
    }

    function renderCategoriesSection() {
      const rootMonthly = document.getElementById("categoryMonthlyList");
      const rootDaily = document.getElementById("categoryDailyList");
      const rootKeywords = document.getElementById("keywordsMonthlyList");
      const categories = state.categories || {};
      const monthlyRows = (categories.category_monthly || []).slice();
      const dailyRows = (categories.category_daily || []).slice();
      const keywordRows = (categories.keywords_monthly || []).slice();
      rootMonthly.innerHTML = monthlyRows.length
        ? monthlyRows.map((row) => `
          <article class="row">
            <div class="row-grid">
              <div><span class="chip">${escapeHtml(monthToJp(row.month))}</span></div>
              <div class="title">${escapeHtml(row.category || "その他")}</div>
              <div class="num"><div class="label">会話数</div><div>${fmtInt(row.conversation_count)}</div></div>
              <div class="num"><div class="label">あなたの発言</div><div>${fmtInt(row.user_message_count)}</div></div>
              <div class="num"><div class="label">AI返答</div><div>${fmtInt(row.assistant_message_count)}</div></div>
              <div class="num"><div class="label">合計</div><div>${fmtInt(row.total_message_count)}</div></div>
            </div>
          </article>
        `).join("")
        : `<div class="empty">カテゴリ月次データがありません。</div>`;
      rootDaily.innerHTML = dailyRows.length
        ? dailyRows.map((row) => `
          <article class="row">
            <div class="row-grid">
              <div><span class="chip">${escapeHtml(row.date.replaceAll("-", "/"))}</span></div>
              <div class="title">${escapeHtml(row.category || "その他")}</div>
              <div class="num"><div class="label">会話数</div><div>${fmtInt(row.conversation_count)}</div></div>
              <div class="num"><div class="label">あなたの発言</div><div>${fmtInt(row.user_message_count)}</div></div>
              <div class="num"><div class="label">AI返答</div><div>${fmtInt(row.assistant_message_count)}</div></div>
              <div class="num"><div class="label">合計</div><div>${fmtInt(row.total_message_count)}</div></div>
            </div>
          </article>
        `).join("")
        : `<div class="empty">カテゴリ日次データがありません。</div>`;
      rootKeywords.innerHTML = keywordRows.length
        ? keywordRows.map((row) => `
          <article class="row">
            <div class="row-grid" style="grid-template-columns: 110px 1fr 120px;">
              <div><span class="chip">${escapeHtml(monthToJp(row.month))}</span></div>
              <div class="title">${escapeHtml(row.keyword || "")}</div>
              <div class="num"><div class="label">出現回数</div><div>${fmtInt(row.count)}</div></div>
            </div>
          </article>
        `).join("")
        : `<div class="empty">キーワードデータがありません。</div>`;
    }

    function loadCategoriesSection() {
      if (state.categoriesLoading || state.categoriesLoaded) return;
      state.categoriesLoading = true;
      setChip("categoriesState", "読み込み中");
      setStatus("categoriesStatus", "カテゴリ詳細JSONを読み込んでいます...");
      fetchJson(FILES.categories)
        .then((data) => {
          state.categories = data;
          state.categoriesLoaded = true;
          state.categoriesLoading = false;
          renderCategoriesSection();
          setChip("categoriesState", "読み込み済み");
          setStatus("categoriesStatus", "読み込み完了");
        })
        .catch((error) => {
          state.categoriesLoading = false;
          setChip("categoriesState", "読み込み失敗");
          setStatus(
            "categoriesStatus",
            `カテゴリ詳細の読み込みに失敗しました。ローカルHTTPサーバーで開いているか確認してください。${error.message}`,
            "error",
          );
        });
    }

    function renderPagedList(containerId, rows, stateKey, rowRenderer, pageSize, emptyMessage) {
      const root = document.getElementById(containerId);
      const visibleCount = state.codexVisibleCounts[stateKey] || pageSize;
      const visibleRows = rows.slice(0, visibleCount);
      if (!rows.length) {
        root.innerHTML = `<div class="empty">${escapeHtml(emptyMessage)}</div>`;
        return;
      }
      root.innerHTML = `
        ${visibleRows.map(rowRenderer).join("")}
        ${rows.length > visibleRows.length ? `<div class="more-wrap"><button type="button" data-more="${stateKey}">さらに表示</button></div>` : ""}
      `;
      const moreBtn = root.querySelector(`[data-more="${stateKey}"]`);
      if (moreBtn) {
        moreBtn.addEventListener("click", () => {
          state.codexVisibleCounts[stateKey] = visibleCount + pageSize;
          renderCodexSection();
        });
      }
    }

    function renderCodexSection() {
      if (!state.codexLoaded || !state.codex) return;
      const summary = state.codex.summary || {};
      const meta = state.codex.meta || {};
      const april = (state.summary?.monthly || []).find((row) => row.month === "2026-04");
      const chatgptThreadCount = april ? Number(april.conversations || 0) : null;
      const codexSessionCount = Number(meta.rollout_file_count || 0);
      document.getElementById("codexSummaryCards").innerHTML = [
        ["ChatGPTスレッド数", chatgptThreadCount == null ? "-" : fmtInt(chatgptThreadCount)],
        ["Codexセッション数", fmtInt(codexSessionCount)],
        ["ChatGPTでのあなたの入力数", fmtInt(summary.chat_codex_prompt_count || 0)],
        ["Codexでのあなたの入力数", fmtInt(summary.codex_user_prompt_count || 0)],
        ["一致数", fmtInt(summary.matched_prompt_count || 0)],
        ["ChatGPT側だけにあるもの", fmtInt(summary.chat_only_prompt_count || 0)],
        ["Codex側だけにあるもの", fmtInt(summary.codex_only_prompt_count || 0)],
      ]
        .map(([label, value]) => `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`)
        .join("");

      renderPagedList(
        "codexMatchedList",
        state.codex.matches || [],
        "matched",
        (row) => `
          <article class="row">
            <div class="row-grid">
              <div>${escapeHtml((row.date_jst || "").replaceAll("-", "/"))}</div>
              <div><span class="chip">${escapeHtml(row.match_type || "matched")}</span></div>
              <div class="num">${escapeHtml(String(row.confidence ?? ""))}</div>
              <div>
                <div>${escapeHtml(row.conversation_title || "")}</div>
                <div class="muted">${escapeHtml((row.rollout_path || "").slice(-96))}</div>
                <div class="snippet">${escapeHtml(row.snippet || "")}</div>
              </div>
            </div>
          </article>
        `,
        30,
        "一致データがありません。",
      );
      renderPagedList(
        "codexChatOnlyList",
        state.codex.unmatched_chat || [],
        "chatOnly",
        (row) => `
          <article class="row">
            <div class="row-grid">
              <div>${escapeHtml((row.date_jst || "").replaceAll("-", "/"))}</div>
              <div><span class="chip">chat_only</span></div>
              <div class="num">${escapeHtml(String(row.confidence ?? ""))}</div>
              <div>
                <div>${escapeHtml(row.conversation_title || "")}</div>
                <div class="muted">${escapeHtml((row.estimated_repo || "").slice(-96))}</div>
                <div class="snippet">${escapeHtml(row.snippet || "")}</div>
              </div>
            </div>
          </article>
        `,
        30,
        "ChatGPT側だけのデータがありません。",
      );
      renderPagedList(
        "codexOnlyList",
        state.codex.unmatched_codex || [],
        "codexOnly",
        (row) => `
          <article class="row">
            <div class="row-grid">
              <div>${escapeHtml((row.date_jst || "").replaceAll("-", "/"))}</div>
              <div><span class="chip">codex_only</span></div>
              <div class="num">${escapeHtml(String(row.confidence ?? ""))}</div>
              <div>
                <div>${escapeHtml(row.cwd_or_repo || "")}</div>
                <div class="muted">${escapeHtml((row.rollout_path || "").slice(-96))}</div>
                <div class="snippet">${escapeHtml(row.snippet || "")}</div>
              </div>
            </div>
          </article>
        `,
        30,
        "Codex側だけのデータがありません。",
      );
      setChip("codexState", "読み込み済み");
      setStatus("codexStatus", `読み込み完了: 一致 ${fmtInt((state.codex.matches || []).length)} 件`);
    }

    function loadCodexSection() {
      if (state.codexLoading || state.codexLoaded) return;
      state.codexLoading = true;
      setChip("codexState", "読み込み中");
      setStatus("codexStatus", "Codex照合JSONを読み込んでいます...");
      fetchJson(FILES.codex)
        .then((data) => {
          state.codex = data;
          state.codexLoaded = true;
          state.codexLoading = false;
          renderCodexSection();
        })
        .catch((error) => {
          state.codexLoading = false;
          setChip("codexState", "読み込み失敗");
          setStatus(
            "codexStatus",
            `Codex照合の読み込みに失敗しました。ローカルHTTPサーバーで開いているか確認してください。${error.message}`,
            "error",
          );
        });
    }

    function bindEvents() {
      document.getElementById("loadConversationsBtn").addEventListener("click", loadConversationSection);
      document.getElementById("loadDailyBtn").addEventListener("click", loadDailySection);
      document.getElementById("loadCategoriesBtn").addEventListener("click", loadCategoriesSection);
      document.getElementById("loadCodexBtn").addEventListener("click", loadCodexSection);
      document.getElementById("titleSearch").addEventListener("input", (e) => {
        state.conversationFilters.titleSearch = e.target.value || "";
        state.conversationVisibleCount = 50;
        renderConversationList();
      });
      document.getElementById("monthFilter").addEventListener("change", (e) => {
        state.conversationFilters.monthFilter = e.target.value;
        state.conversationVisibleCount = 50;
        renderConversationList();
      });
      document.getElementById("categoryFilter").addEventListener("change", (e) => {
        state.conversationFilters.categoryFilter = e.target.value;
        state.conversationVisibleCount = 50;
        renderConversationList();
      });
      document.getElementById("sortBy").addEventListener("change", (e) => {
        state.conversationFilters.sortBy = e.target.value;
        state.conversationVisibleCount = 50;
        renderConversationList();
      });
      document.getElementById("daySelect").addEventListener("change", (e) => {
        state.dailySelected = e.target.value;
        renderDailyTopForSelectedDay();
      });
    }

    async function init() {
      bindEvents();
      try {
        const summary = await fetchJson(FILES.summary);
        state.summary = summary;
        renderMeta(summary);
        renderSummaryCards(summary);
        renderMonthlyList(summary);
        setStatus("summaryStatus", `サマリーを読み込みました。月別 ${fmtInt((summary.monthly || []).length)} 件。`);
      } catch (error) {
        setStatus(
          "summaryStatus",
          `サマリーの読み込みに失敗しました。ローカルHTTPサーバーで開いているか確認してください。${error.message}`,
          "error",
        );
        setChip("summaryPhase", "読み込み失敗");
        return;
      }
      setConversationControlsEnabled(false);
      document.getElementById("conversationList").innerHTML = `<div class="empty">会話一覧はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("dailyList").innerHTML = `<div class="empty">日別詳細はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("categoryMonthlyList").innerHTML = `<div class="empty">カテゴリ詳細はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("keywordsMonthlyList").innerHTML = `<div class="empty">キーワード詳細はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("codexSummaryCards").innerHTML = `<div class="empty">Codex照合はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("codexMatchedList").innerHTML = `<div class="empty">Codex照合はボタンを押したときだけ読み込みます。</div>`;
      document.getElementById("codexChatOnlyList").innerHTML = "";
      document.getElementById("codexOnlyList").innerHTML = "";
      setStatus("conversationStatus", "未読み込み");
      setStatus("dailyStatus", "未読み込み");
      setStatus("categoriesStatus", "未読み込み");
      setStatus("codexStatus", "未読み込み");
    }

    init();
  </script>
</body>
</html>
"""


def write_dashboard_html(path: Path) -> None:
    path.write_text(build_dashboard_html(), encoding="utf-8")


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
    _write_json(output_dir / "dashboard_summary.json", build_dashboard_summary_payload(parsed))
    _write_json(output_dir / "dashboard_conversations.json", build_dashboard_conversations_payload(parsed))
    _write_json(output_dir / "dashboard_daily.json", build_dashboard_daily_payload(parsed))
    _write_json(output_dir / "dashboard_categories.json", build_dashboard_categories_payload(parsed))
    _write_json(output_dir / "dashboard_codex_match.json", build_dashboard_codex_payload(parsed))
    write_monthly_summary_md(output_dir / "monthly_summary.md", parsed)
    write_dashboard_html(output_dir / "dashboard.html")
    write_codex_match_outputs(output_dir, parsed.get("codex_match"))


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
    parser.add_argument(
        "--codex-sessions-root",
        default=str(DEFAULT_CODEX_SESSIONS_ROOT),
        help="Codex sessions root directory (default: ~/.codex/sessions)",
    )
    parser.add_argument(
        "--codex-match-month",
        default=DEFAULT_MATCH_MONTH,
        help="Target month for Codex match report (YYYY-MM)",
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
    local_tz = ensure_timezone(args.timezone)

    if not args.rebuild and should_reuse_parsed(parsed_path, input_files, rules_path):
        try:
            parsed = load_parsed(parsed_path)
            parse_mode = "reused parsed_summary.json"
        except ValueError:
            parsed = collect_stats_from_inputs(input_files, marker, local_tz, rules)
            parse_mode = "parsed raw export (incompatible parsed_summary.json was rebuilt)"
    else:
        parsed = collect_stats_from_inputs(input_files, marker, local_tz, rules)
        parse_mode = "parsed raw export"

    parsed.setdefault("meta", {})
    parsed["meta"]["timezone"] = args.timezone
    parsed["meta"]["input_files"] = [str(p) for p in input_files]
    parsed["meta"]["rules_file"] = str(rules_path)
    parsed["meta"]["generated_at"] = datetime.now().astimezone().isoformat()
    parsed["meta"]["codex_match_month"] = args.codex_match_month
    codex_sessions_root = Path(args.codex_sessions_root).resolve()
    parsed["meta"]["codex_sessions_root"] = str(codex_sessions_root)

    parsed["codex_match"] = build_codex_match_report(
        input_files,
        marker,
        local_tz,
        codex_sessions_root,
        args.codex_match_month,
    )

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
        "out/codex_chat_match_2026-04_summary.md",
        "out/codex_chat_match_2026-04_chat_prompts.csv",
        "out/codex_chat_match_2026-04_codex_prompts.csv",
        "out/codex_chat_match_2026-04_matches.csv",
        "out/codex_chat_match_2026-04_unmatched_chat.csv",
        "out/codex_chat_match_2026-04_unmatched_codex.csv",
    ):
        print(f"  - {output_dir / name}")


if __name__ == "__main__":
    main()

