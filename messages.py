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
    parser.add_argument('files', nargs='+', help='JSONL file(s) to read.')
    args = parser.parse_args()

    max_len = args.max_len
    preserve_newlines = args.preserve_newlines

    for path in args.files:
        path = os.path.expanduser(path)
        fname = os.path.basename(path)

        with open(path) as fh:
            for i, line in enumerate(fh, 1):
                d = json.loads(line.rstrip('\n'))
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


if __name__ == '__main__':
    main()
