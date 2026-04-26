#!/usr/bin/env python3
"""Privacy-safe census of VS Code workspace state keys.

Raw row samples are written only to unsanitized/. Stdout contains aggregate
counts and signal flags so formatter work can be prioritized without committing
local state details.
"""

import argparse
import base64
import gzip
import json
import os
import re
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from env_paths import state_db_candidates


PATH_RE = re.compile(
    r"(?i)(?:[A-Z]:\\[^\s\"<>|]+|/(?:home|users|mnt|var|tmp|etc|opt|workspace|workspaces)/[^\s\"<>|]+|[\w./\\-]+\.(?:py|md|json|jsonl|sqlite|vscdb|txt|ps1|sh|ts|tsx|js|jsx|yaml|yml))"
)
COMMAND_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?`?(?:python|py|git|rg|grep|find|Get-ChildItem|Select-String|npm|pnpm|yarn|pytest|pip|uv|csr)\b")
ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure|denied|missing|timeout|out of memory|heap)\b")
TODO_RE = re.compile(r"(?i)\b(todo|next|follow-up|decision|roadmap|blocked|issue|planned)\b")
TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def decode_value(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        for decoder in (
            lambda b: b.decode("utf-8"),
            lambda b: gzip.decompress(b).decode("utf-8"),
            lambda b: zlib.decompress(b).decode("utf-8"),
        ):
            try:
                return decoder(value)
            except Exception:
                pass
        try:
            return base64.b64encode(value).decode("ascii")
        except Exception:
            return repr(value)
    return str(value)


def parse_jsonish(text):
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(stripped)
    except Exception:
        return None


def shape_of(value):
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    if isinstance(value, bytes):
        return "bytes"
    return type(value).__name__


def byte_len(value):
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8", errors="replace"))


def signal_flags(text):
    text = text or ""
    return {
        "has_path": bool(PATH_RE.search(text)),
        "has_command": bool(COMMAND_RE.search(text)),
        "has_error": bool(ERROR_RE.search(text)),
        "has_todo": bool(TODO_RE.search(text)),
        "has_timestamp": bool(TIMESTAMP_RE.search(text)),
    }


def sanitize_text(text):
    text = str(text or "")
    replacements = []
    for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        value = os.getenv(name)
        if value:
            replacements.append((value, f"%{name}%"))
            replacements.append((value.replace("\\", "/"), f"%{name}%"))
    username = os.getenv("USERNAME") or os.getenv("USER")
    if username:
        replacements.append((f"\\Users\\{username}\\", "\\Users\\<USER>\\"))
        replacements.append((f"/Users/{username}/", "/Users/<USER>/"))
        replacements.append((f"/home/{username}/", "/home/<USER>/"))
    computer = os.getenv("COMPUTERNAME")
    if computer:
        replacements.append((computer, "<COMPUTER>"))

    for old, new in replacements:
        text = text.replace(old, new)
    return text


def sanitize_key(key):
    text = sanitize_text(key)
    lower = text.lower()
    if lower.startswith("resource.authority."):
        return "resource.authority.<REDACTED>"
    if len(text) > 160:
        return text[:120] + "...<REDACTED>"
    return text


def default_raw_path():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return Path("unsanitized") / f"key-census-{stamp}.json"


def collect_census(sample_chars=500):
    stats = defaultdict(lambda: {
        "count": 0,
        "total_bytes": 0,
        "min_bytes": None,
        "max_bytes": 0,
        "value_shapes": Counter(),
        "decoded_shapes": Counter(),
        "json_dict": 0,
        "json_list": 0,
        "has_path": 0,
        "has_command": 0,
        "has_error": 0,
        "has_todo": 0,
        "has_timestamp": 0,
    })
    raw_records = []
    db_count = 0
    row_count = 0

    for db_path in state_db_candidates():
        db_count += 1
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("SELECT key, value FROM ItemTable").fetchall()
        except Exception as exc:
            raw_records.append({
                "db_path": str(db_path),
                "error": repr(exc),
            })
            continue

        for key, value in rows:
            row_count += 1
            decoded = decode_value(value)
            parsed = parse_jsonish(decoded)
            flags = signal_flags(decoded)
            size = byte_len(value)
            item = stats[str(key)]
            item["count"] += 1
            item["total_bytes"] += size
            item["min_bytes"] = size if item["min_bytes"] is None else min(item["min_bytes"], size)
            item["max_bytes"] = max(item["max_bytes"], size)
            item["value_shapes"][shape_of(value)] += 1
            item["decoded_shapes"][shape_of(parsed) if parsed is not None else shape_of(decoded)] += 1
            if isinstance(parsed, dict):
                item["json_dict"] += 1
            elif isinstance(parsed, list):
                item["json_list"] += 1
            for flag, enabled in flags.items():
                if enabled:
                    item[flag] += 1

            raw_records.append({
                "db_path": str(db_path),
                "key": key,
                "value_shape": shape_of(value),
                "decoded_shape": shape_of(parsed) if parsed is not None else shape_of(decoded),
                "bytes": size,
                "signals": flags,
                "sample": (decoded or "")[:sample_chars],
            })

    summary = []
    for key, item in stats.items():
        count = item["count"]
        summary.append({
            "key": sanitize_key(key),
            "count": count,
            "avg_bytes": round(item["total_bytes"] / count, 1) if count else 0,
            "min_bytes": item["min_bytes"] or 0,
            "max_bytes": item["max_bytes"],
            "value_shapes": dict(item["value_shapes"]),
            "decoded_shapes": dict(item["decoded_shapes"]),
            "json_dict": item["json_dict"],
            "json_list": item["json_list"],
            "has_path": item["has_path"],
            "has_command": item["has_command"],
            "has_error": item["has_error"],
            "has_todo": item["has_todo"],
            "has_timestamp": item["has_timestamp"],
        })

    summary.sort(
        key=lambda item: (
            -(item["has_command"] + item["has_error"] + item["has_todo"] + item["has_path"]),
            -item["count"],
            item["key"],
        )
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "state_db_count": db_count,
        "row_count": row_count,
        "keys": summary,
    }, raw_records


def print_table(summary, limit):
    print(f"State DBs scanned: {summary['state_db_count']}")
    print(f"Rows scanned: {summary['row_count']}")
    print()
    print("count  path cmd err todo time  avgB    maxB    key")
    print("-----  ---- --- --- ---- ----  ------  ------  ---")
    for item in summary["keys"][:limit]:
        print(
            f"{item['count']:>5}  "
            f"{item['has_path']:>4} "
            f"{item['has_command']:>3} "
            f"{item['has_error']:>3} "
            f"{item['has_todo']:>4} "
            f"{item['has_timestamp']:>4}  "
            f"{item['avg_bytes']:>6}  "
            f"{item['max_bytes']:>6}  "
            f"{item['key']}"
        )


def filter_summary(summary, patterns=None, only_signal=False):
    patterns = [item.lower() for item in (patterns or []) if item]
    keys = []
    for item in summary["keys"]:
        if patterns and not any(pattern in item["key"].lower() for pattern in patterns):
            continue
        if only_signal and not any(
            item.get(flag, 0) for flag in ("has_path", "has_command", "has_error", "has_todo", "has_timestamp")
        ):
            continue
        keys.append(item)
    return {**summary, "keys": keys}


def main():
    parser = argparse.ArgumentParser(description="Census VS Code state keys without printing raw values.")
    parser.add_argument("--limit", type=int, default=40, help="max keys to print")
    parser.add_argument("--match", action="append", default=[], help="case-insensitive key substring filter; repeatable")
    parser.add_argument("--only-signal", action="store_true", help="only show keys with path/command/error/todo/timestamp signals")
    parser.add_argument("--json", action="store_true", dest="json_out", help="print sanitized JSON summary")
    parser.add_argument("--raw-out", default=str(default_raw_path()), help="raw ignored output path")
    parser.add_argument("--sample-chars", type=int, default=500, help="raw sample chars per row")
    args = parser.parse_args()

    summary, raw_records = collect_census(sample_chars=args.sample_chars)

    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({
        "summary": summary,
        "raw_records": raw_records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    filtered = filter_summary(summary, patterns=args.match, only_signal=args.only_signal)

    if args.json_out:
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
    else:
        print_table(filtered, args.limit)
        print()
        print(f"Raw detail written to ignored path: {sanitize_text(raw_path)}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
