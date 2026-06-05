#!/usr/bin/env python3
"""Estimate active working time from a Claude Code session JSONL file.

Extracts timestamps from all entries and groups them into active work sessions
separated by idle gaps. Reports per-session durations and total active time.

Usage:
    python3 active_time.py FILE.jsonl [FILE2.jsonl ...]
    python3 active_time.py --idle-threshold 15 FILE.jsonl
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta


def extract_timestamps(path):
    timestamps = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            ts = data.get("timestamp") or (data.get("snapshot", {}).get("timestamp"))
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamps.append(dt)
    timestamps.sort()
    return timestamps


def compute_sessions(timestamps, idle_threshold):
    if not timestamps:
        return [], timedelta()

    sessions = []
    session_start = timestamps[0]
    prev_ts = timestamps[0]

    for ts in timestamps[1:]:
        if ts - prev_ts > idle_threshold:
            sessions.append((session_start, prev_ts, prev_ts - session_start))
            session_start = ts
        prev_ts = ts

    sessions.append((session_start, prev_ts, prev_ts - session_start))
    active_time = sum((s[2] for s in sessions), timedelta())
    return sessions, active_time


def format_duration(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


def analyze_file(path, idle_minutes):
    timestamps = extract_timestamps(path)
    if not timestamps:
        print(f"{path}: no timestamps found")
        return

    idle_threshold = timedelta(minutes=idle_minutes)
    sessions, active_time = compute_sessions(timestamps, idle_threshold)

    basename = os.path.basename(path)
    print(f"\n{'=' * 70}")
    print(f"File: {basename}")
    print(f"Entries with timestamps: {len(timestamps)}")
    print(f"First: {timestamps[0].strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Last:  {timestamps[-1].strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Wall clock span: {format_duration(timestamps[-1] - timestamps[0])}")
    print(f"Idle threshold: {idle_minutes} min")
    print()
    print(f"{'#':>3}  {'Start':>16}  {'End':>16}  {'Duration':>12}")
    print("-" * 54)
    for i, (start, end, dur) in enumerate(sessions, 1):
        print(
            f"{i:3}  {start.strftime('%m-%d %H:%M:%S'):>16}"
            f"  {end.strftime('%m-%d %H:%M:%S'):>16}"
            f"  {format_duration(dur):>12}"
        )
    print()
    print(f"Active sessions: {len(sessions)}")
    print(f"Estimated active time: {format_duration(active_time)}"
          f" ({active_time.total_seconds() / 3600:.1f} hours)")


def main():
    parser = argparse.ArgumentParser(
        description="Estimate active working time from Claude Code JSONL files."
    )
    parser.add_argument("files", nargs="+", help="JSONL files to analyze")
    parser.add_argument(
        "--idle-threshold",
        type=int,
        default=30,
        metavar="MINUTES",
        help="Gap in minutes that counts as idle (default: 30)",
    )
    args = parser.parse_args()

    for path in args.files:
        analyze_file(path, args.idle_threshold)


if __name__ == "__main__":
    main()
