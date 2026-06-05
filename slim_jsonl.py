#!/usr/bin/env python3
"""Slim down a JSONL session file by stripping bloat.

Options:
  --images / --no-images          Strip base64 image payloads (default: off)
  --snapshots / --no-snapshots    Drop file-history-snapshot entries (default: off)
  --trim-pre-compaction           Drop all lines before the last compaction boundary (default: off)
  --backup-ref PATH               Rewrite the compaction message to reference this backup path

Usage: python3 slim_jsonl.py INPUT.jsonl OUTPUT.jsonl [options]
"""

import argparse
import json
from pathlib import PurePosixPath
import re
import sys


def strip_images_from_content(content):
    """Recursively find and replace base64 image blocks in message content."""
    if isinstance(content, list):
        new_list = []
        for item in content:
            new_list.append(strip_images_from_content(item))
        return new_list
    if isinstance(content, dict):
        src = content.get("source", {})
        if isinstance(src, dict) and src.get("type") == "base64" and "data" in src:
            media_type = src.get("media_type", "unknown")
            data_len = len(src["data"])
            orig_bytes = data_len * 3 // 4  # approximate decoded size
            return {
                "type": "text",
                "text": f"[image stripped: {media_type}, ~{orig_bytes // 1024}KB]",
            }
        return {k: strip_images_from_content(v) for k, v in content.items()}
    return content


def find_last_compaction(entries):
    """Find the line number of the last compaction system message."""
    last = None
    for i, d in enumerate(entries):
        if d.get("type") == "system":
            msg = d.get("message", d)
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text += b.get("text", "")
            if "compact" in text.lower():
                last = i
    return last


def rewrite_backup_ref(d, backup_path):
    """Rewrite the transcript path in a compaction continuation message."""
    msg = d.get("message", d)
    content = msg.get("content", "")

    def replace_path(text):
        # Match "read the full transcript at: /some/path.jsonl"
        return re.sub(
            r"(read the full transcript at: )\S+\.jsonl",
            rf"\1{backup_path}",
            text,
        )

    if isinstance(content, str):
        msg["content"] = replace_path(content)
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                b["text"] = replace_path(b["text"])


def main():
    parser = argparse.ArgumentParser(description="Slim down a JSONL session file")
    parser.add_argument("input", help="Input JSONL file")
    parser.add_argument("output", help="Output JSONL file")
    parser.add_argument("--images", action=argparse.BooleanOptionalAction, default=False,
                        help="Strip base64 image payloads (default: off)")
    parser.add_argument("--snapshots", action=argparse.BooleanOptionalAction, default=False,
                        help="Drop file-history-snapshot entries (default: off)")
    parser.add_argument("--trim-pre-compaction", action="store_true",
                        help="Drop all lines before the last compaction boundary (default: off)")
    parser.add_argument("--backup-ref", nargs="?", const="auto",
                        help="Rewrite the compaction message to reference a backup path. "
                             "If no path given, auto-derives from the existing ref + input filename suffix.")
    args = parser.parse_args()

    # First pass: load everything if we need to find compaction boundary or rewrite refs
    entries = None
    start_line = 0  # 0-indexed
    if args.trim_pre_compaction or args.backup_ref:
        entries = []
        with open(args.input) as fin:
            for line in fin:
                entries.append(json.loads(line))

        last_compaction = find_last_compaction(entries)
        if last_compaction is not None:
            if args.trim_pre_compaction:
                start_line = last_compaction
                print(f"Trimming: dropping {start_line} lines before last compaction", file=sys.stderr)

            if args.backup_ref:
                # The continuation message is typically the entry right after the compaction
                for j in range(last_compaction + 1, min(last_compaction + 5, len(entries))):
                    text = ""
                    msg = entries[j].get("message", entries[j])
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                text += b.get("text", "")
                    if "read the full transcript at:" in text:
                        backup_path = args.backup_ref
                        if backup_path == "auto":
                            # Extract existing dir from the ref, use input basename
                            m = re.search(r"read the full transcript at: (\S+)", text)
                            if m:
                                existing = PurePosixPath(m.group(1))
                                input_basename = PurePosixPath(args.input).name
                                backup_path = str(existing.parent / input_basename)
                            else:
                                print("Warning: could not find existing path to derive backup ref", file=sys.stderr)
                                break
                        rewrite_backup_ref(entries[j], backup_path)
                        print(f"Rewrote backup reference to: {backup_path}", file=sys.stderr)
                        break
        else:
            print("Warning: no compaction boundary found in file", file=sys.stderr)

    # Main pass
    images_stripped = 0
    snapshots_dropped = 0
    pre_compaction_dropped = 0
    bytes_saved = 0
    lines_written = 0

    with open(args.input) as fin, open(args.output, "w") as fout:
        for i, line in enumerate(fin):
            original_sz = len(line)

            if i < start_line:
                pre_compaction_dropped += 1
                bytes_saved += original_sz
                continue

            # Use pre-parsed entry if we modified it (backup ref rewrite)
            d = entries[i] if entries is not None else json.loads(line)

            if args.snapshots and d.get("type") == "file-history-snapshot":
                snapshots_dropped += 1
                bytes_saved += original_sz
                continue

            if args.images:
                for key in ("message", None):
                    obj = d.get(key) if key else d
                    if isinstance(obj, dict) and "content" in obj:
                        old_content = obj["content"]
                        new_content = strip_images_from_content(old_content)
                        if new_content != old_content:
                            obj["content"] = new_content

            new_line = json.dumps(d, separators=(",", ":"))
            new_sz = len(new_line)
            if new_sz < original_sz:
                saved = original_sz - new_sz
                bytes_saved += saved
                images_stripped += 1

            fout.write(new_line + "\n")
            lines_written += 1

    print(f"Done: {lines_written} lines written")
    print(f"  {images_stripped} entries had images stripped")
    print(f"  {snapshots_dropped} file-history-snapshot entries dropped")
    print(f"  {pre_compaction_dropped} pre-compaction lines dropped")
    print(f"  {bytes_saved / 1024 / 1024:.2f} MB saved")


if __name__ == "__main__":
    main()
