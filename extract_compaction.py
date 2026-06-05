#!/usr/bin/env python3
"""Extract the most recent compaction summary from a Claude Code JSONL transcript.

Compaction summaries are entries with `isCompactSummary: true` (a `user` entry
whose `message.content` holds the summary text that replaces the prior history).
Picks the latest one by timestamp, falling back to file order on ties.

Usage:
  python3 extract_compaction.py FILE.jsonl [-o OUTPUT]
  python3 extract_compaction.py FILE.jsonl --all  (write every summary, numbered)

If no -o is given, output goes to FILE.compaction.txt next to the input.
"""

import argparse
import json
import os
import sys


def extract_text(content):
    """Compaction content is usually a plain string, but tolerate block lists."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)


def find_compactions(path):
    """Yield (line_no, entry_dict) for every compaction-summary entry."""
    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("isCompactSummary") is True:
                yield i, d


def format_summary(line_no, entry):
    msg = entry.get("message", {}) or {}
    text = extract_text(msg.get("content", ""))
    header = [
        f"# Compaction summary",
        f"# line: {line_no}",
        f"# uuid: {entry.get('uuid', '?')}",
        f"# parentUuid: {entry.get('parentUuid', '?')}",
        f"# sessionId: {entry.get('sessionId', '?')}",
        f"# timestamp: {entry.get('timestamp', '?')}",
        "",
    ]
    return "\n".join(header) + text.rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", help="Path to JSONL transcript")
    parser.add_argument("-o", "--output",
                        help="Output file (default: <input>.compaction.txt)")
    parser.add_argument("--all", action="store_true",
                        help="Write every compaction summary, separated and numbered")
    args = parser.parse_args()

    path = os.path.expanduser(args.file)
    summaries = list(find_compactions(path))

    if not summaries:
        print(f"No compaction summaries found in {path}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output
    if not out_path:
        base, _ = os.path.splitext(path)
        out_path = f"{base}.compaction.txt"

    if args.all:
        chunks = []
        for n, (ln, entry) in enumerate(summaries, 1):
            chunks.append(f"=== Summary {n} of {len(summaries)} ===\n")
            chunks.append(format_summary(ln, entry))
            chunks.append("\n")
        body = "".join(chunks)
    else:
        # Most recent: latest timestamp, ties broken by file order (last wins).
        line_no, entry = max(
            summaries,
            key=lambda pair: (pair[1].get("timestamp") or "", pair[0]),
        )
        body = format_summary(line_no, entry)

    with open(out_path, "w") as f:
        f.write(body)

    count = len(summaries) if args.all else 1
    noun = "summaries" if count != 1 else "summary"
    print(f"Wrote {count} {noun} ({len(body)} chars) to {out_path}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
