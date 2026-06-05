#!/usr/bin/env python3
"""Analyze conversation structure: compaction boundaries, image/tool-result sizes, chain segments."""

import json
import sys


def analyze(path):
    entries = []
    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            entries.append((i, json.loads(line), len(line)))

    # Find compaction boundaries (system messages after which parentUuid chain restarts)
    compactions = []
    images_total = 0
    images_count = 0
    tool_results_total = 0
    tool_results_count = 0
    tool_results_by_name = {}

    for ln, d, sz in entries:
        t = d.get("type")
        msg = d.get("message", d)
        content = msg.get("content", "")

        # Detect compaction: system messages with summary content
        if t == "system":
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += block.get("text", "")
            if "compact" in text.lower() or "summary" in text.lower() or d.get("parentUuid") is None:
                compactions.append((ln, sz, text[:200]))

        # Count images
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    src = block.get("source", {})
                    if src.get("type") == "base64":
                        data = src.get("data", "")
                        images_total += len(data)
                        images_count += 1
                    # Count tool results
                    if block.get("type") == "tool_result":
                        tr_content = block.get("content", "")
                        tr_sz = len(json.dumps(tr_content))
                        tool_results_total += tr_sz
                        tool_results_count += 1
                        tool_id = block.get("tool_use_id", "?")
                        # Try to find the tool name from prior assistant message
                        tool_results_by_name[tool_id] = tr_sz

    # Find chain segments (parentUuid=None starts)
    chain_starts = []
    for ln, d, sz in entries:
        if d.get("type") in ("user", "assistant", "system"):
            parent = d.get("parentUuid")
            if parent is None or str(parent) == "None":
                chain_starts.append((ln, d.get("type"), d.get("uuid", "?")[:12]))

    # Count entries by size bucket
    buckets = {"<1KB": 0, "1-10KB": 0, "10-100KB": 0, "100KB-1MB": 0, ">1MB": 0}
    for ln, d, sz in entries:
        if sz < 1024:
            buckets["<1KB"] += 1
        elif sz < 10240:
            buckets["1-10KB"] += 1
        elif sz < 102400:
            buckets["10-100KB"] += 1
        elif sz < 1048576:
            buckets["100KB-1MB"] += 1
        else:
            buckets[">1MB"] += 1

    # Size of entries >100KB (candidates for truncation)
    large_entries = [(ln, d.get("type"), sz) for ln, d, sz in entries if sz > 102400]

    print(f"Compaction/chain-restart boundaries ({len(compactions)}):")
    for ln, sz, text in compactions:
        print(f"  L{ln}: {sz} bytes - {text[:120]}...")
    print()

    print(f"Chain starts (parentUuid=None) ({len(chain_starts)}):")
    for ln, t, uuid in chain_starts:
        print(f"  L{ln}: [{t}] uuid={uuid}")
    print()

    print(f"Images: {images_count} images, {images_total/1024/1024:.2f} MB total base64")
    print(f"Tool results: {tool_results_count} results, {tool_results_total/1024/1024:.2f} MB total")
    print()

    print("Entry size distribution:")
    for bucket, count in buckets.items():
        print(f"  {bucket:15s}: {count}")
    print()

    print(f"Entries > 100KB ({len(large_entries)}):")
    for ln, t, sz in large_entries:
        print(f"  L{ln:5d}: {sz/1024/1024:7.2f} MB  [{t}]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} FILE.jsonl", file=sys.stderr)
        sys.exit(1)
    analyze(sys.argv[1])
