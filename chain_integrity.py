#!/usr/bin/env python3
"""Check chain integrity: walk from tail to root, report where and why the chain ends.

Reports:
  - Chain length and endpoints
  - Whether the root is a compaction boundary or an orphan
  - All compaction boundaries in the file and whether they're on-chain
  - Whether the chain is broken (parent not found)

Usage: python3 chain_integrity.py FILE.jsonl
"""

import json
import sys


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} FILE.jsonl", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]

    uuid_to_entry = {}
    entries = []
    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            d = json.loads(line)
            d["_line"] = i
            entries.append(d)
            uuid = d.get("uuid")
            if uuid:
                uuid_to_entry[uuid] = d

    # Find tail
    tail = None
    for d in reversed(entries):
        if d.get("uuid") and d.get("type") in ("user", "assistant", "system"):
            tail = d
            break

    if not tail:
        print("No message with UUID found in file", file=sys.stderr)
        sys.exit(1)

    # Walk chain
    chain = []
    current = tail
    seen = set()
    broken_parent = None
    while current:
        uuid = current.get("uuid")
        if not uuid or uuid in seen:
            break
        seen.add(uuid)
        chain.append(current)
        parent = current.get("parentUuid")
        if parent is None or str(parent) == "None":
            break
        parent_entry = uuid_to_entry.get(str(parent))
        if not parent_entry:
            broken_parent = str(parent)
            break
        current = parent_entry

    chain.reverse()
    root = chain[0]

    def get_text(d, max_len=200):
        msg = d.get("message", d)
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    text += b.get("text", "")
        return text.replace("\n", " ")[:max_len]

    print(f"File: {len(entries)} lines")
    print(f"Chain: {len(chain)} entries")
    print()
    print(f"Tail: L{tail['_line']} [{tail.get('type')}] uuid={str(tail.get('uuid'))[:12]}")
    print(f"  ep={tail.get('entrypoint','')} ver={tail.get('version','')}")
    print(f"  {get_text(tail)}")
    print()
    print(f"Root: L{root['_line']} [{root.get('type')}] uuid={str(root.get('uuid'))[:12]} parentUuid={root.get('parentUuid')}")
    print(f"  ep={root.get('entrypoint','')} ver={root.get('version','')}")
    print(f"  {get_text(root)}")
    print()

    if broken_parent:
        # Find who has the broken parent
        breaker = chain[-1]
        print(f"** CHAIN BROKEN at L{breaker['_line']}: parent {broken_parent[:12]} not found in file **")
    elif root.get("parentUuid") is None or str(root.get("parentUuid")) == "None":
        print(f"Chain reaches root (parentUuid=None)")
    print()

    # Find all compaction boundaries
    compactions = []
    for d in entries:
        if d.get("type") == "system":
            text = get_text(d)
            if "compact" in text.lower():
                compactions.append(d)

    print(f"Compaction boundaries in file: {len(compactions)}")
    for d in compactions:
        on_chain = d.get("uuid") in seen
        print(f"  L{d['_line']}: uuid={str(d.get('uuid',''))[:12]} "
              f"parent={str(d.get('parentUuid','None'))[:12]} "
              f"{'ON CHAIN' if on_chain else 'OFF CHAIN'}")
    print()

    # Count on-chain vs off-chain messages
    on_chain_msgs = sum(1 for d in entries if d.get("uuid") in seen and d.get("type") in ("user", "assistant", "system"))
    off_chain_msgs = sum(1 for d in entries if d.get("uuid") and d.get("uuid") not in seen and d.get("type") in ("user", "assistant", "system"))
    print(f"Messages on chain: {on_chain_msgs}")
    print(f"Messages off chain: {off_chain_msgs}")
    print()

    # Forks: on-chain entries with 2+ children
    children_count = {}
    for d in entries:
        parent = d.get("parentUuid")
        if parent:
            children_count[str(parent)] = children_count.get(str(parent), 0) + 1

    forks = [(d, children_count[d["uuid"]]) for d in entries
             if d.get("uuid") in seen and children_count.get(d.get("uuid"), 0) > 1]
    print(f"Forks (on-chain entries with 2+ children): {len(forks)}")
    for d, n_children in forks:
        print(f"  L{d['_line']}: [{d.get('type')}] uuid={str(d.get('uuid',''))[:12]} "
              f"ep={d.get('entrypoint','')} children={n_children}")
        print(f"    {get_text(d, 100)}")
    print()

    # Entrypoint switches along the chain
    ep_switches = []
    prev_ep = ""
    for d in chain:
        ep = d.get("entrypoint", "")
        if ep and prev_ep and ep != prev_ep:
            ep_switches.append((d, prev_ep, ep))
        if ep:
            prev_ep = ep
    print(f"Entrypoint switches on chain: {len(ep_switches)}")
    for d, old_ep, new_ep in ep_switches:
        print(f"  L{d['_line']}: {old_ep} -> {new_ep}  [{d.get('type')}]")
        print(f"    {get_text(d, 100)}")


if __name__ == "__main__":
    main()
