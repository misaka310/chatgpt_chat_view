from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

CHUNK_SIZE = 1024 * 1024
CHAT_HTML_MARKER = "var jsonData ="


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
                    keep = buf[-(len(marker) - 1):] if len(marker) > 1 else ""
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
    raise FileNotFoundError("No input file found. Put chat.html, conversations.json, or conversations-*.json in input/.")


def ensure_timezone(tz_name: Optional[str]):
    if tz_name and ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    if tz_name in (None, "", "UTC", "Etc/UTC"):
        return timezone.utc
    if tz_name == "Asia/Tokyo":
        return timezone(timedelta(hours=9), name="Asia/Tokyo")
    raise RuntimeError(f"Timezone '{tz_name}' could not be resolved.")


def pick_timestamp(message: dict) -> Optional[float]:
    for key in ("create_time", "update_time"):
        value = message.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def normalize_role(role: Optional[str]) -> str:
    value = (role or "").strip().lower()
    if value in {"user", "assistant", "system", "tool"}:
        return value
    return "other"


def safe_title(value: Any, fallback: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            text_parts = [str(part).strip() for part in parts if isinstance(part, (str, int, float)) and str(part).strip()]
            if text_parts:
                return "\n".join(text_parts)
        text_value = content.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()
    if isinstance(content, list):
        text_parts = [str(part).strip() for part in content if isinstance(part, (str, int, float)) and str(part).strip()]
        if text_parts:
            return "\n".join(text_parts)
    return ""


def extract_message_text(message: dict) -> str:
    return extract_text_from_content(message.get("content"))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def build_message_dedupe_key(conv_id: str, message: dict, role: str, text: str) -> str:
    message_id = message.get("id")
    if isinstance(message_id, str) and message_id.strip():
        return f"{conv_id}::id::{message_id.strip()}"
    timestamp = pick_timestamp(message)
    payload = f"{role}\n{timestamp}\n{normalize_text(text)[:1200]}\n{normalize_text(str(message.get('recipient') or ''))}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"{conv_id}::fallback::{digest}"
