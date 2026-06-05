#!/usr/bin/env python3
"""Trace the parentUuid chain backwards from the tail of a JSONL file.

Shows what Claude actually sees when resuming a session — walks from the
last message with a UUID backwards through parentUuid links until the chain
breaks or reaches a root (parentUuid=None).

Usage: python3 trace_chain.py FILE.jsonl [--limit N]
"""

import json
import sys
import argparse
from datetime import datetime


def format_ts(d):
    ts = d.get("timestamp")
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts = ts / 1000
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        return str(ts)
    except Exception:
        return "?"


def get_text_preview(d, max_len=120):
    msg = d.get("message", d)
    content = msg.get("content", "")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("source", {}).get("type") == "base64":
                    parts.append("[image]")
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool:{block.get('name','?')}]")
                elif block.get("type") == "tool_result":
                    parts.append("[tool_result]")
        text = " ".join(parts)
    else:
        text = str(content)
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def main():
    parser = argparse.ArgumentParser(description="Trace parentUuid chain from tail")
    parser.add_argument("file", help="JSONL file path")
    parser.add_argument("--limit", type=int, default=0, help="Max entries to trace (0=unlimited)")
    parser.add_argument("--messages-only", action="store_true",
                        help="Only print user/assistant/system messages, skip progress/file-history-snapshot/etc.")
    args = parser.parse_args()

    # Load all entries with UUIDs, indexed by uuid
    uuid_to_entry = {}
    all_entries = []
    with open(args.file) as fh:
        for i, line in enumerate(fh, 1):
            d = json.loads(line)
            d["_line"] = i
            all_entries.append(d)
            uuid = d.get("uuid")
            if uuid:
                uuid_to_entry[uuid] = d

    # Find the last entry with a uuid (the tail of the conversation)
    tail = None
    for d in reversed(all_entries):
        if d.get("uuid") and d.get("type") in ("user", "assistant", "system"):
            tail = d
            break

    if not tail:
        print("No message with UUID found in file", file=sys.stderr)
        sys.exit(1)

    # Walk backwards
    chain = []
    current = tail
    seen = set()
    while current:
        uuid = current.get("uuid")
        if uuid in seen:
            chain.append(("CYCLE", current))
            break
        seen.add(uuid)
        chain.append(("OK", current))

        parent_uuid = current.get("parentUuid")
        if parent_uuid is None or str(parent_uuid) == "None":
            chain.append(("ROOT", current))
            break

        parent = uuid_to_entry.get(str(parent_uuid))
        if not parent:
            chain.append(("BROKEN", current))
            break

        current = parent

        if args.limit and len(chain) >= args.limit:
            chain.append(("LIMIT", current))
            break

    # Reverse to show chronological order
    chain.reverse()

    print(f"Chain length: {len(chain)} entries (from tail at L{tail['_line']})")
    print(f"{'=' * 80}")

    message_types = {"user", "assistant", "system"}
    for i, (status, d) in enumerate(chain):
        ln = d.get("_line", "?")
        t = d.get("type", "?")
        ts = format_ts(d)
        uuid = str(d.get("uuid", "?"))[:12]
        parent = str(d.get("parentUuid", "None"))[:12]
        preview = get_text_preview(d)

        marker = ""
        if status == "ROOT":
            continue  # duplicate of the last OK entry
        elif status == "BROKEN":
            marker = " ** BROKEN (parent not found) **"
        elif status == "CYCLE":
            marker = " ** CYCLE **"
        elif status == "LIMIT":
            marker = " ** LIMIT **"

        is_first = (i == 0)
        is_last = (i == len(chain) - 1)
        is_boundary = status in ("BROKEN", "CYCLE", "LIMIT")

        if args.messages_only and t not in message_types:
            if not (is_first or is_last or is_boundary):
                continue

        print(f"  L{ln:<6d} [{t:9s}] {ts}  uuid={uuid} parent={parent}")
        if preview:
            print(f"           {preview}")
        if marker:
            print(f"           {marker}")
        print()


if __name__ == "__main__":
    main()
