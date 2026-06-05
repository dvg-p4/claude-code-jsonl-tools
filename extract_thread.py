#!/usr/bin/env python3
"""Extract a conversation thread from a JSONL file by line range or UUID chain.

Outputs human-readable conversation with timestamps, roles, and content.
Strips base64 image data and tool-result binary payloads for readability.

Usage:
  python3 extract_thread.py FILE.jsonl --lines START END
  python3 extract_thread.py FILE.jsonl --from-uuid UUID  (walks parentUuid chain forward)
"""

import json
import sys
import argparse
from datetime import datetime


def extract_text(content, max_tool_result=500):
    """Extract readable text from message content, truncating tool results."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)[:200]

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            btype = block.get("type", "")
            if btype == "text":
                parts.append(block.get("text", ""))
            elif btype == "image" or (block.get("source", {}).get("type") == "base64"):
                media = block.get("source", {}).get("media_type", "image")
                parts.append(f"[{media} image]")
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                inp_str = json.dumps(inp, indent=2)
                if len(inp_str) > max_tool_result:
                    inp_str = inp_str[:max_tool_result] + "..."
                parts.append(f"[tool_use: {name}]\n{inp_str}")
            elif btype == "tool_result":
                tool_id = block.get("tool_use_id", "?")
                tr_content = block.get("content", "")
                tr_text = extract_text(tr_content, max_tool_result)
                if len(tr_text) > max_tool_result:
                    tr_text = tr_text[:max_tool_result] + f"... [{len(tr_text)} chars total]"
                parts.append(f"[tool_result for {tool_id[:20]}]\n{tr_text}")
            else:
                text = block.get("text", block.get("content", ""))
                if isinstance(text, str) and text:
                    parts.append(text)
    return "\n".join(parts)


def format_timestamp(d):
    ts = d.get("timestamp")
    if ts:
        try:
            if isinstance(ts, (int, float)):
                # Could be seconds or milliseconds
                if ts > 1e12:
                    ts = ts / 1000
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            return str(ts)
        except Exception:
            return "?"
    return ""


def main():
    parser = argparse.ArgumentParser(description="Extract conversation thread from JSONL")
    parser.add_argument("file", help="JSONL file path")
    parser.add_argument("--lines", nargs=2, type=int, metavar=("START", "END"),
                        help="Line range (inclusive)")
    parser.add_argument("--from-uuid", help="Start from this UUID and walk forward")
    parser.add_argument("--types", default="user,assistant,system",
                        help="Comma-separated entry types to include (default: user,assistant,system)")
    parser.add_argument("--max-tool", type=int, default=500,
                        help="Max chars for tool result content (default: 500)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = parser.parse_args()

    allowed_types = set(args.types.split(","))

    entries = []
    with open(args.file) as fh:
        for i, line in enumerate(fh, 1):
            entries.append((i, json.loads(line)))

    # Filter by line range
    if args.lines:
        start, end = args.lines
        entries = [(ln, d) for ln, d in entries if start <= ln <= end]

    # Filter by UUID chain (walk forward from given UUID)
    if args.from_uuid:
        uuid_to_entry = {}
        children = {}  # parent_uuid -> [child entries]
        for ln, d in entries:
            uuid = d.get("uuid")
            parent = d.get("parentUuid")
            if uuid:
                uuid_to_entry[uuid] = (ln, d)
            if parent:
                children.setdefault(str(parent), []).append((ln, d))

        # Walk forward from the given UUID
        chain = []
        queue = [args.from_uuid]
        seen = set()
        while queue:
            uid = queue.pop(0)
            if uid in seen:
                continue
            seen.add(uid)
            if uid in uuid_to_entry:
                chain.append(uuid_to_entry[uid])
            for child_ln, child_d in children.get(uid, []):
                child_uuid = child_d.get("uuid")
                if child_uuid:
                    queue.append(child_uuid)
        entries = sorted(chain, key=lambda x: x[0])

    # Format output
    out_lines = []
    for ln, d in entries:
        t = d.get("type", "?")
        if t not in allowed_types:
            continue

        msg = d.get("message", d)
        role = msg.get("role", t)
        content = msg.get("content", "")
        text = extract_text(content, args.max_tool)
        ts = format_timestamp(d)

        header = f"--- L{ln} [{role}] {ts} ---"
        out_lines.append(header)
        out_lines.append(text)
        out_lines.append("")

    output = "\n".join(out_lines)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Wrote {len(out_lines)} lines to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
