#!/usr/bin/env python3
"""Inspect the structure of the largest entries in a JSONL file."""

import json
import sys


def summarize_content(content, depth=0):
    """Recursively summarize content structure."""
    indent = "  " * depth
    if isinstance(content, str):
        return f"{indent}str ({len(content)} chars)"
    if isinstance(content, list):
        lines = [f"{indent}list ({len(content)} items):"]
        for i, item in enumerate(content[:5]):
            lines.append(f"{indent}  [{i}]: {summarize_content(item, depth+2).strip()}")
        if len(content) > 5:
            lines.append(f"{indent}  ... and {len(content)-5} more")
        return "\n".join(lines)
    if isinstance(content, dict):
        lines = [f"{indent}dict:"]
        for k, v in content.items():
            val_summary = summarize_content(v, depth+2).strip()
            if len(val_summary) < 120:
                lines.append(f"{indent}  {k}: {val_summary}")
            else:
                lines.append(f"{indent}  {k}:")
                lines.append(summarize_content(v, depth+2))
        return "\n".join(lines)
    return f"{indent}{type(content).__name__}: {repr(content)[:100]}"


def inspect(path, top_n=5):
    entries = []
    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            entries.append((len(line), i, line))

    entries.sort(reverse=True)

    for sz, ln, line in entries[:top_n]:
        d = json.loads(line)
        print(f"{'=' * 72}")
        print(f"  L{ln}: {sz/1024/1024:.2f} MB  type={d.get('type')}")
        print(f"  uuid={d.get('uuid', '?')[:12]}  parent={str(d.get('parentUuid', '?'))[:12]}")
        print(f"{'=' * 72}")

        # For user entries, look at the message content structure
        msg = d.get("message", d)
        role = msg.get("role", "?")
        content = msg.get("content", "")

        print(f"  role: {role}")
        print(summarize_content(content, depth=1))
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} FILE.jsonl [TOP_N]", file=sys.stderr)
        sys.exit(1)
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    inspect(sys.argv[1], top_n)
