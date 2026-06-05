#!/usr/bin/env python3
"""
Print a readable conversation from a Claude Code session JSONL file.

Shows only user and assistant messages, truncated to a configurable length.

Usage:
    python3 messages.py [-n MAX_LEN] FILE.jsonl [FILE2.jsonl ...]
"""

import argparse
import json
import os
import sys


def extract_text(msg):
    """Extract plain text from a message field."""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get('content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get('type') == 'text':
                    parts.append(item.get('text', ''))
            return '\n'.join(parts)
    return str(msg)


def main():
    parser = argparse.ArgumentParser(
        description='Print a readable conversation from a Claude Code session JSONL file.'
    )
    parser.add_argument(
        '-n', '--max-len',
        type=int,
        default=400,
        help='Truncate each message to this many characters (default: 400; 0 for no truncation).',
    )
    parser.add_argument(
        '--preserve-newlines',
        action='store_true',
        help='Preserve newlines within messages; put the message body on the line after the [USER]/[CLAUDE] label.',
    )
    parser.add_argument(
        '--skip-invalid',
        action='store_true',
        help='Silently skip lines that are not valid JSON. Useful when piping through grep -A/-B/-C, which inserts "--" separators.',
    )
    parser.add_argument('files', nargs='+', help='JSONL file(s) to read. Use "-" for stdin.')
    args = parser.parse_args()

    max_len = args.max_len
    preserve_newlines = args.preserve_newlines

    for path in args.files:
        if path == '-':
            fh = sys.stdin
            close = False
        else:
            fh = open(os.path.expanduser(path))
            close = True

        try:
            for i, line in enumerate(fh, 1):
                stripped = line.rstrip('\n')
                if args.skip_invalid:
                    try:
                        d = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                else:
                    d = json.loads(stripped)
                t = d.get('type')
                if t not in ('user', 'assistant'):
                    continue

                text = extract_text(d.get('message', ''))
                if not text.strip():
                    continue

                label = 'USER' if t == 'user' else 'CLAUDE'
                if max_len > 0 and len(text) > max_len:
                    truncated = text[:max_len] + '...'
                else:
                    truncated = text

                if preserve_newlines:
                    print(f"[{label}]")
                    print(truncated.strip())
                else:
                    truncated = truncated.replace('\n', ' ').strip()
                    print(f"[{label}] {truncated}")
                print()
        finally:
            if close:
                fh.close()


if __name__ == '__main__':
    main()
