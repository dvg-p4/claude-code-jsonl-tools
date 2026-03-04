#!/usr/bin/env python3
"""
Print a slim tab-separated view of each line in a session JSONL file.

Usage:
    python3 slim.py FILE.jsonl
    python3 slim.py FILE.jsonl | column -ts$'\t'
"""

import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    paths = [os.path.expanduser(p) for p in sys.argv[1:]]
    cols = ['timestamp', 'file', 'line', 'type', 'sessionId', 'slug', 'uuid', 'parentUuid', 'messageId']
    print('\t'.join(cols))

    for path in paths:
        fname = os.path.basename(path)
        with open(path) as fh:
            for i, line in enumerate(fh, 1):
                d = json.loads(line.rstrip('\n'))
                ts = d.get('timestamp')
                t = d.get('type', '')
                sid = d.get('sessionId')
                slug = d.get('slug')
                uuid = d.get('uuid')
                parent = d.get('parentUuid')
                mid = d.get('messageId')

                print('\t'.join(str(v) for v in [ts, fname, i, t, sid, slug, uuid, parent, mid]))


if __name__ == '__main__':
    main()
