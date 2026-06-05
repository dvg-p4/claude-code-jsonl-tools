#!/usr/bin/env python3
"""Analyze JSONL file size distribution by entry type and identify largest lines."""

import json
import sys


def analyze(path):
    type_sizes = {}
    type_counts = {}
    biggest = []

    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            sz = len(line)
            d = json.loads(line)
            t = d.get("type", "?")
            type_sizes[t] = type_sizes.get(t, 0) + sz
            type_counts[t] = type_counts.get(t, 0) + 1
            biggest.append((sz, i, t))

    biggest.sort(reverse=True)
    total = sum(type_sizes.values())

    print(f"{'=' * 72}")
    print(f"  {path}")
    print(f"{'=' * 72}")
    print()
    print("  Size by type:")
    for t in sorted(type_sizes, key=type_sizes.get, reverse=True):
        pct = type_sizes[t] / total * 100
        print(
            f"    {t:30s} {type_sizes[t]/1024/1024:8.2f} MB"
            f"  ({type_counts[t]:4d} entries, {pct:5.1f}%)"
        )
    print(f"    {'TOTAL':30s} {total/1024/1024:8.2f} MB")
    print()
    print("  Top 10 largest lines:")
    for sz, ln, t in biggest[:10]:
        print(f"    L{ln:5d}: {sz/1024/1024:7.2f} MB  [{t}]")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} FILE.jsonl [FILE2.jsonl ...]", file=sys.stderr)
        sys.exit(1)
    for path in sys.argv[1:]:
        analyze(path)
