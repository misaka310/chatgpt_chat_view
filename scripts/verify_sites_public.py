#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

PUBLIC_SOURCE_FILES = {"favicon.svg", "usage-data.json"}
TOP_LEVEL_KEYS = {"schema_version", "generated_at", "timezone", "method", "totals", "monthly", "daily"}
TOTAL_KEYS = {"sent_messages", "non_voice_messages", "voice_messages", "active_days", "non_voice_active_days", "voice_active_days", "conversation_count", "estimated_tokens"}
MONTH_KEYS = {"month", "sent_messages", "non_voice_messages", "voice_messages", "active_days", "non_voice_active_days", "voice_active_days", "conversation_count", "estimated_tokens"}
DAY_KEYS = {"date", "month", "day", "sent_messages", "non_voice_messages", "voice_messages", "conversation_count", "estimated_tokens"}
ALLOWED_TEXT_SUFFIXES = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt"}
ALLOWED_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"}
ALLOWED_EXTENSIONLESS_ARTIFACTS = {"client/.assetsignore", "client/_headers", "server/BUILD_ID"}
FIXED_METHOD = "ChatGPTエクスポートをPC内で解析し、全件・音声除外・音声のみの送信回数など、本文を含まない数値だけを許可リスト方式で抽出しています。"

FORBIDDEN_PATTERNS = (
    ("conversation export filename", re.compile(r"\bconversations(?:-[^\s\"'<>]+)?\.json\b", re.IGNORECASE)),
    ("private field", re.compile(r"\b(?:conversation_id|message_id|node_id|source_path)\b", re.IGNORECASE)),
    ("private collection", re.compile(r"\bconversations\b", re.IGNORECASE)),
    ("chat export filename", re.compile(r"\bchat\.html\b", re.IGNORECASE)),
    ("Windows absolute path", re.compile(r"\b[A-Za-z]:[\\/]")),
    ("Windows user profile", re.compile(r"\bUsers[\\/][^\\/\s\"'<>]+", re.IGNORECASE)),
    ("email address", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("generic secret assignment", re.compile(r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)),
)


def fail(message: str) -> None:
    raise SystemExit(message)


def non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail(f"invalid public numeric field: {label}")
    return value


def verify_usage_data(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing public aggregate data: {path}")
    except json.JSONDecodeError:
        fail("public aggregate data is not valid JSON")
    if not isinstance(payload, dict) or set(payload) != TOP_LEVEL_KEYS:
        fail("public aggregate data top-level allowlist mismatch")
    if payload.get("schema_version") != 2:
        fail("unsupported public aggregate schema")
    if payload.get("timezone") != "Asia/Tokyo":
        fail("unexpected public aggregate timezone")
    if payload.get("method") != FIXED_METHOD:
        fail("public aggregate method text is not the fixed safe value")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or len(generated_at) < 16 or len(generated_at) > 64:
        fail("invalid public aggregate generated_at")

    totals = payload.get("totals")
    if not isinstance(totals, dict) or set(totals) != TOTAL_KEYS:
        fail("public totals allowlist mismatch")
    for key, value in totals.items():
        non_negative_int(value, f"totals.{key}")

    monthly = payload.get("monthly")
    if not isinstance(monthly, list) or not monthly:
        fail("public monthly rows are missing")
    months: list[str] = []
    for index, row in enumerate(monthly):
        if not isinstance(row, dict) or set(row) != MONTH_KEYS:
            fail(f"public monthly row allowlist mismatch at index {index}")
        month = row.get("month")
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
            fail(f"invalid public month at index {index}")
        months.append(month)
        for key in MONTH_KEYS - {"month"}:
            non_negative_int(row.get(key), f"monthly[{index}].{key}")
        if row["sent_messages"] != row["non_voice_messages"] + row["voice_messages"]:
            fail(f"public monthly message modes do not add up at index {index}")
    if months != sorted(set(months)):
        fail("public monthly rows are not unique and sorted")

    daily = payload.get("daily")
    if not isinstance(daily, list) or not daily:
        fail("public daily rows are missing")
    dates: list[str] = []
    for index, row in enumerate(daily):
        if not isinstance(row, dict) or set(row) != DAY_KEYS:
            fail(f"public daily row allowlist mismatch at index {index}")
        date = row.get("date")
        month = row.get("month")
        day = row.get("day")
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])", date):
            fail(f"invalid public date at index {index}")
        if month != date[:7] or month not in months:
            fail(f"invalid public daily month at index {index}")
        if day != int(date[8:]):
            fail(f"invalid public day number at index {index}")
        dates.append(date)
        for key in DAY_KEYS - {"date", "month"}:
            non_negative_int(row.get(key), f"daily[{index}].{key}")
        if row["sent_messages"] != row["non_voice_messages"] + row["voice_messages"]:
            fail(f"public daily message modes do not add up at index {index}")
    if dates != sorted(set(dates)):
        fail("public daily rows are not unique and sorted")

    if totals["sent_messages"] != totals["non_voice_messages"] + totals["voice_messages"]:
        fail("public total message modes do not add up")
    if totals["sent_messages"] != sum(row["sent_messages"] for row in monthly):
        fail("public total sent messages does not match monthly rows")
    if totals["non_voice_messages"] != sum(row["non_voice_messages"] for row in monthly):
        fail("public total non-voice messages does not match monthly rows")
    if totals["voice_messages"] != sum(row["voice_messages"] for row in monthly):
        fail("public total voice messages does not match monthly rows")
    if totals["estimated_tokens"] != sum(row["estimated_tokens"] for row in monthly):
        fail("public total estimated tokens does not match monthly rows")
    if totals["active_days"] != sum(1 for row in daily if row["sent_messages"] > 0):
        fail("public total active days does not match daily rows")
    if totals["non_voice_active_days"] != sum(1 for row in daily if row["non_voice_messages"] > 0):
        fail("public total non-voice active days does not match daily rows")
    if totals["voice_active_days"] != sum(1 for row in daily if row["voice_messages"] > 0):
        fail("public total voice active days does not match daily rows")
    return payload


def public_files(root: Path) -> list[Path]:
    if not root.is_dir():
        fail(f"public root is missing: {root}")
    result = []
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"symlink is not allowed in public artifacts: {path.relative_to(root)}")
        if path.is_file():
            result.append(path)
    return sorted(result)


def verify_public_source(root: Path) -> None:
    names = {path.relative_to(root).as_posix() for path in public_files(root)}
    if names != PUBLIC_SOURCE_FILES:
        extra = sorted(names - PUBLIC_SOURCE_FILES)
        missing = sorted(PUBLIC_SOURCE_FILES - names)
        fail(f"public source allowlist mismatch; extra={extra}; missing={missing}")


def verify_artifact_file_types(root: Path, files: Iterable[Path]) -> None:
    count = 0
    for path in files:
        count += 1
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        if suffix in {".map", ".log", ".csv"}:
            fail(f"forbidden artifact type: {relative}")
        if relative in ALLOWED_EXTENSIONLESS_ARTIFACTS:
            if relative == "server/BUILD_ID":
                build_id = path.read_text(encoding="utf-8").strip()
                if not re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                    build_id,
                    re.IGNORECASE,
                ):
                    fail("invalid server/BUILD_ID artifact")
            continue
        if suffix not in ALLOWED_TEXT_SUFFIXES | ALLOWED_BINARY_SUFFIXES:
            fail(f"unapproved artifact type: {relative}")
    if count == 0:
        fail("public artifact directory is empty")


def collect_private_markers(private_output_dir: Path) -> set[str]:
    markers: set[str] = set()
    for name in ("dashboard_conversations.json", "dashboard_daily.json", "dashboard_summary.json"):
        path = private_output_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stack: list[Any] = [payload]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"conversation_id", "title", "input_files", "source_path"}:
                        if isinstance(item, str) and len(item.strip()) >= 4:
                            markers.add(item.strip())
                        elif isinstance(item, list):
                            for child in item:
                                if isinstance(child, str) and len(child.strip()) >= 4:
                                    markers.add(child.strip())
                    stack.append(item)
            elif isinstance(value, list):
                stack.extend(value)
    return markers


def scan_text(root: Path, files: Iterable[Path], private_markers: set[str]) -> None:
    failures: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if (
            path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES
            and relative not in ALLOWED_EXTENSIONLESS_ARTIFACTS
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"non-UTF-8 text artifact: {relative}")
            continue
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{label} detected in {relative}")
        if any(marker in text for marker in private_markers):
            failures.append(f"private title, identifier, path, or input name detected in {relative}")
    if failures:
        fail("public artifact inspection failed:\n- " + "\n- ".join(sorted(set(failures))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the Sites deployment contains only allowlisted aggregate data.")
    parser.add_argument("--public-source", type=Path, default=Path("sites/usage-dashboard/public"))
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--private-output-dir", type=Path, default=Path("output"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    public_source = args.public_source.resolve()
    verify_public_source(public_source)
    verify_usage_data(public_source / "usage-data.json")
    private_markers = collect_private_markers(args.private_output_dir.resolve())
    source_files = public_files(public_source)
    scan_text(public_source, source_files, private_markers)

    checked_files = len(source_files)
    if args.artifact_root:
        artifact_root = args.artifact_root.resolve()
        artifact_files = public_files(artifact_root)
        verify_artifact_file_types(artifact_root, artifact_files)
        scan_text(artifact_root, artifact_files, private_markers)
        checked_files += len(artifact_files)

    print(f"Sites public artifact inspection passed ({checked_files} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
