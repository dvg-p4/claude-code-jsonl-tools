#!/usr/bin/env python3
"""
Print a readable conversation from a Claude Code session JSONL file.

Shows only user and assistant messages, truncated to 400 characters each.

Usage:
    python3 messages.py FILE.jsonl [FILE2.jsonl ...]
"""

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
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    max_len = 400

    for path in sys.argv[1:]:
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
                truncated = text[:max_len] + '...' if len(text) > max_len else text
                # Collapse to single line for readability
                truncated = truncated.replace('\n', ' ').strip()

                print(f"[{label}] {truncated}")
                print()


if __name__ == '__main__':
    main()
