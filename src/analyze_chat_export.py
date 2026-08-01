#!/usr/bin/env python3
from __future__ import annotations

from chat_export_core import (
    build_message_dedupe_key,
    detect_inputs,
    ensure_timezone,
    extract_message_text,
    normalize_role,
    pick_timestamp,
    safe_title,
    stream_json_array,
)
from analyze_chat_export_public import main


if __name__ == "__main__":
    main()
