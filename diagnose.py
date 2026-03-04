#!/usr/bin/env python3
"""
Diagnose cross-contamination in Claude Code session JSONL files.

Usage:
    python3 diagnose.py FILE1.jsonl [FILE2.jsonl ...]

For each file, reports:
- Line count and entry type distribution
- Session IDs present (owner vs foreign)
- Custom-title entries and whether they're correct
- Broken parentUuid chains
- Foreign entry locations and content previews

When multiple files are given, also checks for cross-file UUID references.
"""

import json
import os
import sys
import collections


def extract_content_preview(d, max_len=100):
    """Extract a short content preview from a message entry."""
    t = d.get('type')
    if t == 'custom-title':
        return f"title={d.get('customTitle', '?')!r}"
    if t in ('user', 'assistant', 'system'):
        m = d.get('message', d.get('content', ''))
        if isinstance(m, dict):
            c = m.get('content', '')
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        return item.get('text', '')[:max_len]
            else:
                return str(c)[:max_len]
        elif isinstance(m, str):
            return m[:max_len]
        return str(m)[:max_len]
    return ''


def analyze_file(path):
    """Analyze a single JSONL file and return a diagnostic report dict."""
    fname = os.path.basename(path)
    own_sid = fname.replace('.jsonl', '')

    entries = []
    with open(path) as fh:
        for i, line in enumerate(fh, 1):
            d = json.loads(line.rstrip('\n'))
            entries.append((i, d))

    types = collections.Counter()
    sid_counts = collections.Counter()
    titles = []
    uuids_seen = set()
    uuid_lines = collections.defaultdict(list)  # uuid -> [line_nums]
    broken_chains = []
    foreign_entries = []

    for line_num, d in entries:
        t = d.get('type', '?')
        types[t] += 1

        sid = d.get('sessionId', '')
        if sid:
            sid_counts[sid] += 1

        uuid = d.get('uuid')
        parent = d.get('parentUuid')
        if uuid:
            uuids_seen.add(uuid)
            uuid_lines[uuid].append(line_num)
        if parent and str(parent) != 'None' and parent not in uuids_seen:
            broken_chains.append((line_num, d))

        if t == 'custom-title':
            titles.append((line_num, d.get('sessionId', '?'), d.get('customTitle', '?')))

        if sid and sid != own_sid:
            foreign_entries.append((line_num, d))

    duplicate_uuids = {u: lines for u, lines in uuid_lines.items() if len(lines) > 1}

    return {
        'path': path,
        'fname': fname,
        'own_sid': own_sid,
        'total_lines': len(entries),
        'types': dict(types),
        'sid_counts': dict(sid_counts),
        'titles': titles,
        'uuids': uuids_seen,
        'broken_chains': broken_chains,
        'foreign_entries': foreign_entries,
        'duplicate_uuids': duplicate_uuids,
        'entries': entries,
    }


def print_file_report(report):
    """Print the diagnostic report for a single file."""
    own_sid = report['own_sid']
    short_sid = own_sid[:12]

    print(f"{'=' * 72}")
    print(f"  {report['fname']}  ({report['total_lines']} lines)")
    print(f"  Owner session: {own_sid}")
    print(f"{'=' * 72}")

    # Types
    print(f"\n  Entry types:")
    for t, count in sorted(report['types'].items(), key=lambda x: -x[1]):
        print(f"    {t:30s} {count:5d}")

    # Session IDs
    print(f"\n  Session IDs:")
    for sid, count in sorted(report['sid_counts'].items(), key=lambda x: -x[1]):
        marker = 'OWNER' if sid == own_sid else 'FOREIGN'
        print(f"    {sid[:12]}...  x{count:4d}  [{marker}]")

    own_count = report['sid_counts'].get(own_sid, 0)
    foreign_count = sum(c for s, c in report['sid_counts'].items() if s != own_sid)
    if foreign_count:
        print(f"    --> {foreign_count} foreign entries detected!")
    else:
        print(f"    --> Clean (no foreign entries)")

    # Titles
    if report['titles']:
        print(f"\n  Custom-title entries:")
        for line_num, sid, title in report['titles']:
            marker = ''
            if sid != own_sid:
                if sid == '?':
                    marker = ' [NO SESSION ID]'
                else:
                    marker = f' [FOREIGN - belongs to {sid[:12]}...]'
            # Check if title matches a foreign session's expected topic
            print(f"    L{line_num:5d}: sid={sid[:12]}...  title={title!r}{marker}")
    else:
        print(f"\n  Custom-title entries: NONE")

    # Broken chains
    if report['broken_chains']:
        print(f"\n  Broken parentUuid chains ({len(report['broken_chains'])}):")
        for line_num, d in report['broken_chains'][:10]:
            t = d.get('type')
            sid = d.get('sessionId', '')[:12]
            parent = d.get('parentUuid', '')[:12]
            print(f"    L{line_num:5d}: [{t}] sid={sid}...  parent={parent}... NOT FOUND")
        if len(report['broken_chains']) > 10:
            print(f"    ... and {len(report['broken_chains']) - 10} more")
    else:
        print(f"\n  Broken parentUuid chains: NONE")

    # Duplicate UUIDs
    dupes = report['duplicate_uuids']
    if dupes:
        print(f"\n  Duplicate UUIDs ({len(dupes)}):")
        for uuid, lines in list(dupes.items())[:10]:
            print(f"    {uuid[:12]}...  on lines {lines}")
        if len(dupes) > 10:
            print(f"    ... and {len(dupes) - 10} more")
    else:
        print(f"\n  Duplicate UUIDs: NONE")

    # Foreign entry details
    if report['foreign_entries']:
        print(f"\n  Foreign entries ({len(report['foreign_entries'])}):")
        # Group by sessionId
        by_sid = collections.defaultdict(list)
        for line_num, d in report['foreign_entries']:
            by_sid[d.get('sessionId', '?')].append((line_num, d))

        for sid, entries in sorted(by_sid.items()):
            print(f"\n    From {sid[:12]}... ({len(entries)} entries):")
            # Show first and last few
            show = entries[:3] + ([('...', None)] if len(entries) > 6 else []) + entries[-3:] if len(entries) > 6 else entries
            for item in show:
                if item[0] == '...':
                    print(f"      ...")
                    continue
                line_num, d = item
                t = d.get('type')
                preview = extract_content_preview(d)
                uuid_info = ''
                if d.get('uuid'):
                    uuid_info = f" uuid={d['uuid'][:12]}..."
                print(f"      L{line_num:5d}: [{t}]{uuid_info}")
                if preview:
                    print(f"              {preview}")

    print()


def print_cross_file_report(reports):
    """Check for UUID references between files."""
    if len(reports) < 2:
        return

    print(f"{'=' * 72}")
    print(f"  Cross-file UUID analysis")
    print(f"{'=' * 72}")

    uuid_to_file = {}
    for r in reports:
        for u in r['uuids']:
            uuid_to_file[u] = r['fname']

    for r in reports:
        cross_refs = []
        for line_num, d in r['entries']:
            parent = d.get('parentUuid')
            if parent and str(parent) != 'None' and parent not in r['uuids']:
                if parent in uuid_to_file:
                    cross_refs.append((line_num, d, uuid_to_file[parent]))

        if cross_refs:
            print(f"\n  {r['fname'][:12]}... has {len(cross_refs)} parentUuid refs to other files:")
            for line_num, d, target_file in cross_refs[:5]:
                parent = d.get('parentUuid', '')[:12]
                print(f"    L{line_num:5d}: parent={parent}... -> {target_file[:12]}...")
            if len(cross_refs) > 5:
                print(f"    ... and {len(cross_refs) - 5} more")

    # UUID overlap
    for i, r1 in enumerate(reports):
        for r2 in reports[i + 1:]:
            overlap = r1['uuids'] & r2['uuids']
            only_1 = r1['uuids'] - r2['uuids']
            only_2 = r2['uuids'] - r1['uuids']
            print(f"\n  {r1['fname'][:12]}... vs {r2['fname'][:12]}...:")
            print(f"    UUIDs only in first:  {len(only_1)}")
            print(f"    UUIDs only in second: {len(only_2)}")
            print(f"    UUIDs in both:        {len(overlap)}")

    print()


def short_sid(sid):
    """First 8 chars of a session ID for display."""
    return sid[:8] if sid else '?'


def print_timeline(reports):
    """Reconstruct and print a timeline of what happened across all files."""
    if len(reports) < 2:
        return

    print(f"{'=' * 72}")
    print(f"  TIMELINE RECONSTRUCTION")
    print(f"{'=' * 72}")

    # Build a global UUID index: uuid -> (file_owner_sid, line_num, d)
    uuid_index = {}
    # Also build uuid -> sessionId mapping across all files (for snapshot attribution)
    uuid_to_sid = {}
    for r in reports:
        for line_num, d in r['entries']:
            uuid = d.get('uuid')
            sid = d.get('sessionId', '')
            if uuid:
                if uuid not in uuid_index:
                    uuid_index[uuid] = (r['own_sid'], line_num, d)
                if sid and uuid not in uuid_to_sid:
                    uuid_to_sid[uuid] = sid

    # Build session labels from titles
    # For each session, prefer titles from their OWN file, and prefer earlier
    # entries (before contamination can overwrite them)
    session_labels = {}
    # First pass: titles from each session's own file
    for r in reports:
        for _, sid, title in r['titles']:
            if sid == r['own_sid']:
                # First title in own file wins (later ones may be contaminated)
                if sid not in session_labels:
                    session_labels[sid] = title
    # Second pass: titles from foreign entries (only if we don't have one yet)
    for r in reports:
        for _, sid, title in r['titles']:
            if sid and sid != '?' and sid not in session_labels:
                session_labels[sid] = title
    # Fallback labels
    for r in reports:
        if r['own_sid'] not in session_labels:
            session_labels[r['own_sid']] = f"(untitled)"

    # Build slug-to-session mapping and slug legend
    # slug is a per-session identifier assigned after the first API call
    slug_sessions = collections.defaultdict(set)  # slug -> set of sessionIds it wrote
    slug_files = collections.defaultdict(set)      # slug -> set of files it wrote to
    session_slugs = collections.defaultdict(set)   # sessionId -> set of slugs that wrote it
    for r in reports:
        for line_num, d in r['entries']:
            slug = d.get('slug', '')
            sid = d.get('sessionId', '')
            if slug and sid:
                slug_sessions[slug].add(sid)
                slug_files[slug].add(r['fname'])
                session_slugs[sid].add(slug)

    # Print session legend
    print(f"\n  Sessions:")
    all_sids = set()
    for r in reports:
        all_sids.add(r['own_sid'])
        for sid in r['sid_counts']:
            all_sids.add(sid)
    for sid in sorted(all_sids):
        label = session_labels.get(sid, '(unknown)')
        owner_files = [r['fname'][:12] for r in reports if r['own_sid'] == sid]
        file_info = f" -> {owner_files[0]}..." if owner_files else " -> NO OWN FILE"
        slugs = session_slugs.get(sid, set())
        slug_info = f"  slugs: {', '.join(sorted(slugs))}" if slugs else ""
        print(f"    {short_sid(sid)}  {label!r}{file_info}")
        if slug_info:
            print(f"             {slug_info}")

    # Print slug legend (slug is a per-session identifier, assigned after first API call)
    if slug_sessions:
        print(f"\n  Slugs (per-session identifier):")
        for slug in sorted(slug_sessions):
            sids = slug_sessions[slug]
            files = slug_files[slug]
            sid_list = ', '.join(short_sid(s) for s in sorted(sids))
            file_list = ', '.join(f[:12] + '...' for f in sorted(files))
            print(f"    {slug}")
            print(f"      wrote sessionIds: {sid_list}")
            print(f"      wrote to files:   {file_list}")

    # For each contaminated file, reconstruct the event sequence
    for r in reports:
        foreign_sids = {s for s in r['sid_counts'] if s != r['own_sid']}
        if not foreign_sids:
            continue

        print(f"\n  {'- ' * 36}")
        print(f"  Events in {r['fname'][:12]}...  (owner: {short_sid(r['own_sid'])})")
        print(f"  {'- ' * 36}")

        # Walk through the file, tracking session boundaries and key events
        current_sid = None
        current_slug = None
        current_snapshot_sid = None  # which session snapshots are referencing
        region_start = None
        region_count = 0
        dup_block_announced = False
        events = []  # list of (line_num, event_type, detail)

        for line_num, d in r['entries']:
            t = d.get('type')
            sid = d.get('sessionId', '')
            slug = d.get('slug', '')
            ts = d.get('timestamp', '')[:19]
            uuid = d.get('uuid', '')

            # Track file-history-snapshot attribution via messageId
            if t == 'file-history-snapshot':
                mid = d.get('messageId', '')
                if mid:
                    snap_sid = uuid_to_sid.get(mid, '')
                    if snap_sid and snap_sid != current_snapshot_sid:
                        old_label = short_sid(current_snapshot_sid) if current_snapshot_sid else '(none)'
                        new_label = short_sid(snap_sid)
                        own_tag = 'OWN' if snap_sid == r['own_sid'] else 'FOREIGN'
                        events.append((line_num, 'snapshot_shift',
                            f"  SNAPSHOT ATTRIBUTION SHIFT: "
                            f"messageIds now reference {own_tag} session "
                            f"{new_label} (was {old_label})"))
                        current_snapshot_sid = snap_sid
                continue

            # Skip progress entries
            if t == 'progress':
                continue

            is_foreign = sid and sid != r['own_sid']
            entry_label = short_sid(sid) if sid else '?'

            # Detect slug changes
            if slug and slug != current_slug:
                if current_slug is not None:
                    events.append((line_num, 'slug_change',
                        f"  SLUG CHANGE: {current_slug} -> {slug}"))
                current_slug = slug

            # Detect session boundary transitions
            if sid and sid != current_sid:
                # Close previous region
                if current_sid is not None and region_count > 0:
                    owner_tag = 'OWN' if current_sid == r['own_sid'] else 'FOREIGN'
                    events.append((region_start, 'region_end',
                        f"  end {owner_tag} region ({short_sid(current_sid)}): "
                        f"{region_count} entries"))
                # Open new region
                current_sid = sid
                region_start = line_num
                region_count = 0
                owner_tag = 'OWN' if current_sid == r['own_sid'] else 'FOREIGN'
                slug_note = f"  [slug: {current_slug}]" if current_slug else ""
                events.append((line_num, 'region_start',
                    f"  begin {owner_tag} region ({short_sid(current_sid)}){slug_note}"))

            if sid:
                region_count += 1

            # Detect key events within the file
            if t == 'custom-title':
                title = d.get('customTitle', '?')
                target_sid = d.get('sessionId', '?')
                if target_sid == r['own_sid']:
                    events.append((line_num, 'title',
                        f"  TITLE for own session: {title!r}"))
                else:
                    events.append((line_num, 'title_foreign',
                        f"  TITLE for foreign {short_sid(target_sid)}: {title!r}"))

            elif t == 'user':
                # Check for /rename, /compact, /fork commands
                preview = extract_content_preview(d, max_len=200)
                if '<command-name>/rename' in preview:
                    events.append((line_num, 'rename',
                        f"  /rename by {entry_label} at {ts}"))
                elif '<command-name>/compact' in preview:
                    events.append((line_num, 'compact',
                        f"  /compact by {entry_label} at {ts}"))
                elif '<command-name>/fork' in preview:
                    events.append((line_num, 'fork',
                        f"  /fork by {entry_label} at {ts}"))

            # Detect broken parent chain
            parent = d.get('parentUuid')
            if parent and str(parent) != 'None' and uuid:
                if parent not in r['uuids']:
                    # Where does the parent live?
                    if parent in uuid_index:
                        parent_file_sid, parent_line, parent_d = uuid_index[parent]
                        parent_ts = parent_d.get('timestamp', '')[:19]
                        events.append((line_num, 'broken_chain',
                            f"  BROKEN CHAIN: parent {parent[:12]}... lives in "
                            f"{short_sid(parent_file_sid)}'s file (L{parent_line}, {parent_ts})"))
                    else:
                        events.append((line_num, 'broken_chain',
                            f"  BROKEN CHAIN: parent {parent[:12]}... not found anywhere"))

            # Detect start of duplicate block (fire once, on the first
            # second-occurrence line we encounter)
            if uuid and uuid in r['duplicate_uuids'] and not dup_block_announced:
                occurrences = r['duplicate_uuids'][uuid]
                if line_num != occurrences[0]:
                    dup_block_announced = True
                    # Check if parent changed on the first duplicated UUID
                    first_line = occurrences[0]
                    first_d = None
                    for ln, dd in r['entries']:
                        if ln == first_line:
                            first_d = dd
                            break
                    first_parent = str(first_d.get('parentUuid') or '') if first_d else ''
                    this_parent = str(parent or '')
                    parent_note = ''
                    if first_parent != this_parent:
                        fp = first_parent[:12] if first_parent else 'None'
                        tp = this_parent[:12] if this_parent else 'None'
                        parent_note = f" (first entry parent changed: {fp} -> {tp})"
                    # Find the line range of the duplicate block
                    dup_last_line = max(
                        occ[-1] for occ in r['duplicate_uuids'].values()
                    )
                    events.append((line_num, 'dup_start',
                        f"  DUPLICATE BLOCK: {len(r['duplicate_uuids'])} UUIDs from "
                        f"L{occurrences[0]}-region repeated at L{line_num}-L{dup_last_line}"
                        f"{parent_note}"))

        # Close final region
        if current_sid is not None and region_count > 0:
            owner_tag = 'OWN' if current_sid == r['own_sid'] else 'FOREIGN'
            events.append((region_start, 'region_end',
                f"  end {owner_tag} region ({short_sid(current_sid)}): "
                f"{region_count} entries"))

        # Now print events in order, deduplicating region_end with next region_start
        # and adding timestamps from the file
        prev_type = None
        for line_num, etype, detail in events:
            if etype == 'region_end':
                continue  # fold into region_start
            # Get timestamp for this line
            ts = ''
            for ln, d in r['entries']:
                if ln == line_num:
                    ts = d.get('timestamp', '')[:19]
                    break
            ts_str = f"  {ts}" if ts else '                   '

            print(f"    L{line_num:5d}{ts_str}  {detail}")

        # Identify orphaned conversation segments
        print()
        for foreign_sid in foreign_sids:
            # Find UUIDs for this foreign session that exist ONLY in this file
            foreign_uuids_here = set()
            for line_num, d in r['entries']:
                if d.get('sessionId') == foreign_sid and d.get('uuid'):
                    foreign_uuids_here.add(d['uuid'])

            # Check which of these also exist in the foreign session's own file
            foreign_report = None
            for r2 in reports:
                if r2['own_sid'] == foreign_sid:
                    foreign_report = r2
                    break

            if foreign_report:
                also_in_own = foreign_uuids_here & foreign_report['uuids']
                only_here = foreign_uuids_here - foreign_report['uuids']

                # Get timestamp range for orphaned entries
                orphan_times = []
                for line_num, d in r['entries']:
                    if d.get('uuid') in only_here:
                        t = d.get('timestamp', '')
                        if t:
                            orphan_times.append(t[:19])

                if only_here:
                    print(f"    ORPHANED DATA: {len(only_here)} entries from {short_sid(foreign_sid)} "
                          f"exist ONLY in this file (not in their own file)")
                    if orphan_times:
                        print(f"      Time range: {min(orphan_times)} to {max(orphan_times)}")
                    print(f"      These entries will be LOST if foreign data is simply deleted!")

                    # Identify the conversation content that would be lost
                    orphan_messages = []
                    for line_num, d in r['entries']:
                        if d.get('uuid') in only_here and d.get('type') in ('user', 'assistant'):
                            preview = extract_content_preview(d, max_len=80)
                            if preview:
                                orphan_messages.append((line_num, d.get('type'), preview))
                    if orphan_messages:
                        print(f"      Key messages that would be lost:")
                        show = orphan_messages[:3] + orphan_messages[-2:] if len(orphan_messages) > 5 else orphan_messages
                        shown_lines = set()
                        for ln, role, preview in show:
                            if ln not in shown_lines:
                                shown_lines.add(ln)
                                print(f"        L{ln:5d} [{role}] {preview}")
                        if len(orphan_messages) > 5:
                            print(f"        ... and {len(orphan_messages) - len(shown_lines)} more")
                else:
                    print(f"    Foreign data from {short_sid(foreign_sid)}: all {len(also_in_own)} entries "
                          f"also exist in their own file (safe to remove)")

    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    paths = [os.path.expanduser(p) for p in sys.argv[1:]]
    for p in paths:
        if not os.path.exists(p):
            print(f"ERROR: {p} not found")
            sys.exit(1)

    reports = [analyze_file(p) for p in paths]

    for r in reports:
        print_file_report(r)

    if len(reports) > 1:
        print_cross_file_report(reports)
        print_timeline(reports)

    # Summary
    print(f"{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    for r in reports:
        foreign = sum(c for s, c in r['sid_counts'].items() if s != r['own_sid'])
        broken = len(r['broken_chains'])
        bad_titles = sum(1 for _, sid, _ in r['titles'] if sid != r['own_sid'])
        dupes = len(r['duplicate_uuids'])
        status = 'CLEAN' if (foreign == 0 and broken == 0 and bad_titles == 0 and dupes == 0) else 'CONTAMINATED'
        print(f"  {r['fname'][:12]}...: {status}")
        if foreign:
            print(f"    - {foreign} foreign entries")
        if broken:
            print(f"    - {broken} broken parentUuid chain(s)")
        if bad_titles:
            print(f"    - {bad_titles} incorrect custom-title(s)")
        if dupes:
            print(f"    - {dupes} duplicate UUID(s)")
    print()


if __name__ == '__main__':
    main()
