# Claude Code Session JSONL Cross-Contamination Bug

## Summary

After using `/resume` to switch between sessions within the TUI, the system continues writing entries (messages, `file-history-snapshot` records, `custom-title` records) to the **previously active session's JSONL file** instead of the newly resumed session's file. The entries carry the correct `sessionId` but land in the wrong file, corrupting conversation chains, overwriting titles, and making sessions appear blank on resume even though the JSONL data is intact on disk. `/compact` and `/rename` can also trigger or compound the contamination.

## How session storage works

- Each session is a `.jsonl` file in `~/.claude/projects/<project-slug>/`, named `<session-uuid>.jsonl`.
- Each line is a JSON object with a `type` field (`user`, `assistant`, `system`, `progress`, `file-history-snapshot`, `custom-title`, etc.).
- Messages with UUIDs form a chain via `parentUuid` — the resume/display code walks this chain backwards from the tail to reconstruct the conversation.
- `custom-title` entries store the display name for a session (set by `/rename` or auto-generated). They have a `sessionId` field indicating which session they belong to.
- Forked sessions (`/fork`) write into the parent's JSONL file with the fork's `sessionId`. The fork also gets its own `.jsonl` file, but it can be a redundant copy — the parent file may be fully self-contained.
- There is no separate index file (`sessions-index.json`) in all environments. The JSONL files are the sole source of truth.
- Compaction replaces the conversation history with a summary, starting a fresh `parentUuid` chain from `parentUuid=None`.

## The bugs

### 1. Compaction writes to the wrong file

When session B is compacted, the compaction entries (system message, user continuation message, `/compact` command) can be appended to session A's JSONL file instead of session B's, with session B's `sessionId`. This was confirmed in a minimal repro (OXYGEN/NITROGEN test).

### 2. `/rename` cross-contaminates `custom-title` entries

When session A is renamed, `custom-title` entries for *other* sessions get written into session A's file, stamped with the *current* session's title rather than the other session's correct title. This causes the resume picker to display the wrong name for other sessions.

### 3. `parentUuid` chain breaks across sessions

After cross-contamination, a message in session A's file may have a `parentUuid` pointing to a UUID that only exists in session B's (or C's) file. The chain-walking code can't find the parent, so the entire conversation history becomes unreachable. The session appears blank on resume.

### 4. Fork data interleaving confuses the auto-titler

When a fork writes into the parent's file, the parent file ends up with `custom-title` entries for both sessions. The auto-titler (which runs on session save) doesn't filter by `sessionId` — it picks up the fork's title and applies it to the parent, overwriting `/rename` titles.

### 5. `/rename` titles don't persist

Known upstream issue ([#25090](https://github.com/anthropics/claude-code/issues/25090)). `/rename` writes a `custom-title` to the JSONL, but the auto-titling logic runs again on the next session save and overwrites it.

## How to diagnose

### Check for cross-contamination

```bash
# Find entries with foreign sessionIds in a file
python3 -c "
import json, os
f = 'PATH_TO_JSONL'
own_sid = os.path.basename(f).replace('.jsonl', '')[:12]
with open(f) as fh:
    for i, line in enumerate(fh, 1):
        d = json.loads(line)
        sid = d.get('sessionId', '')[:12]
        if sid and sid != own_sid:
            print(f'L{i}: [{d.get(\"type\")}] sid={sid}')
"
```

### Check for broken parentUuid chains

```bash
python3 -c "
import json
f = 'PATH_TO_JSONL'
uuids = set()
with open(f) as fh:
    for i, line in enumerate(fh, 1):
        d = json.loads(line)
        uuid = d.get('uuid')
        parent = d.get('parentUuid')
        if uuid: uuids.add(uuid)
        if parent and str(parent) != 'None' and parent not in uuids:
            print(f'BROKEN L{i}: [{d.get(\"type\")}] parent={parent[:12]} not found')
"
```

### Check custom-title entries

```bash
python3 -c "
import json
f = 'PATH_TO_JSONL'
with open(f) as fh:
    for i, line in enumerate(fh, 1):
        d = json.loads(line)
        if d.get('type') == 'custom-title':
            print(f'L{i}: sid={d.get(\"sessionId\",\"?\")[:12]} title={d.get(\"customTitle\",\"?\")}')
"
```

## Repair strategies

### Remove foreign entries

If a session has entries from an unrelated session (not a fork), remove them:

```python
# Remove lines where sessionId doesn't match the file's own session
# (be careful to preserve legitimate fork-child entries)
```

See `repair_34c527e6.py` for a working example.

### Fix broken parentUuid chains

If removing foreign entries doesn't fix the chain (because the break is at a different point), patch the orphaned message's `parentUuid` to point to the last valid UUID before the break.

### Rebuild a session from scratch

When the file is too tangled (e.g., fork data interleaved with parent data, multiple sessionIds, cross-contaminated titles), the nuclear option is:

1. Trace the `parentUuid` chain backwards from the most recent message
2. The chain naturally stops at the last compaction boundary (the compaction summary contains the full prior context)
3. Write all chained messages to a new JSONL file with a fresh session UUID
4. Replace all `sessionId` fields with the new UUID, strip `forkedFrom` fields
5. Append a correct `custom-title` entry

See `rebuild_session.py` for a working example. This was used to untangle `34c527e6` (which had 9000+ lines with interleaved fork data from `5dd94d59`) into a clean 196-line session.

## The root trigger: `/resume`

### Minimal reproduction (confirmed 2026-03-04)

1. In a fresh project directory, run `claude` and send at least one message. Exit.
2. Run `claude` again to start a new session. Send at least one message. Exit.
3. Run `claude --resume` and pick either session. (This creates a stub `.jsonl` file with a single `file-history-snapshot` line.)
4. Send a message — it goes to the correct session's file.
5. Run `/resume` and pick the *other* session.
6. Send a message — **it goes to the wrong file** (the file from step 3-4, not the resumed session's file).

This is purely sequential, single-process, single-terminal. No concurrency, no `/compact`, no `/rename`, no `/fork` required. The write target simply doesn't follow the `/resume`.

### What the JSONL data shows

- `file-history-snapshot` entries (which carry no `sessionId` or `slug`) are the **first** thing to leak — they appear in the wrong file before any full message entries do.
- The `slug` field (a per-session identifier assigned after the first API call) confirms that the entries are from the correct session — they just land in the wrong file.
- `--resume` from the CLI creates a stub session file (single `file-history-snapshot` line) as a side effect. This stub's `messageId` references the resumed session's messages.
- After `/resume` switches to a different session, new entries continue being appended to the *previously active* file, not the newly resumed session's file.
- The bug is **persistent once triggered** — all subsequent writes within the same process continue going to the wrong file, including system-generated entries like `file-history-snapshot`.
- A **cancelled `/resume`** (selecting a session then pressing Escape or otherwise aborting) still creates a stub `.jsonl` file for the selected session and can shift the write target to the wrong file.

### Relationship to compact/rename contamination

The earlier reproduction steps (compact → rename triggering cross-contamination) may be manifestations of the same underlying bug — `/compact` and `/rename` both trigger save operations that could interact with the same broken write-target logic. However, they may also involve additional bugs (e.g., the auto-titler ignoring `sessionId` per #27202). We haven't ruled out separate code paths.

### Earlier reproduction steps (still valid)

Confirmed minimal repro using compact/rename:

1. Start session A in a project, send a message
2. Exit, start session B in the same project, send a message
3. Exit, resume session A, `/compact`
4. Exit, resume session B, `/compact`
5. `/rename` session B

After step 4-5, session A's JSONL will contain entries from session B's compaction, and `custom-title` entries with the wrong sessionId/title.

A fork is NOT required to trigger the bug, but a fork makes it much worse because the fork legitimately writes into the parent's file, creating permanent interleaving that confuses the title resolution code.

## Related upstream issues

- [#26964](https://github.com/anthropics/claude-code/issues/26964) — canonical "JSONL cross-session contamination" issue (concurrent sessions). #29342 was duped to this.
- [#29342](https://github.com/anthropics/claude-code/issues/29342) — "session transcript writes to wrong JSONL file" (closed as dup of #26964)
- [#27202](https://github.com/anthropics/claude-code/issues/27202) — `/rename` applies title to wrong session; scanner ignores `sessionId` field on `custom-title` entries
- [#25090](https://github.com/anthropics/claude-code/issues/25090) — renamed session titles don't persist after second resume
- [#27422](https://github.com/anthropics/claude-code/issues/27422) — conversations disappear from UI despite JSONL existing on disk
- [#28922](https://github.com/anthropics/claude-code/issues/28922) — `.claude.json` race condition (related pattern, different file)
- [#9668](https://github.com/anthropics/claude-code/issues/9668) — duplicate titles and loading wrong conversations

- [#30802](https://github.com/anthropics/claude-code/issues/30802) — **our issue**: `/resume` writes entries to wrong JSONL file, single-process, no concurrency required

None of the other existing issues identify `/resume` as a single-process trigger. They all assume concurrent sessions or attribute the bug to `/rename`/`/compact`.

## Confirmed affected sessions

- `34c527e6` / `5dd94d59` (docker, `-src` project) — fork interleaving + compaction contamination. Repaired via `rebuild_session.py`.
- `525cdc87` / `902c3cda` (docker, `-src` project) — `/resume` + `/rename` triggered contamination. 71 foreign entries, 33 duplicated, orphaned data.
- `89606e56` / `64f247c3` (local, `sandbox-3`) — `/resume` triggered contamination. 6 foreign entries, orphaned data.
- `7a0de4b4` / `8eb76498` (local, `sandbox-5`) — minimal `/resume` repro. 2 foreign entries, orphaned data.

## Files in this directory

- `diagnose.py` — general-purpose diagnostic tool. Reports foreign entries, broken chains, duplicate UUIDs, snapshot attribution shifts, slug tracking, orphaned data detection, and timeline reconstruction. Usage: `python3 diagnose.py FILE1.jsonl [FILE2.jsonl ...]`
- `slim.py` — prints a tab-separated slim view of JSONL entries (timestamp, file, line, type, sessionId, slug, uuid, parentUuid, messageId). Designed for `sort` and `column -ts$'\t'`. Usage: `python3 slim.py FILE1.jsonl [FILE2.jsonl ...]`
- `one_off/` — (gitignored) one-off repair/analysis scripts with hardcoded paths for specific incidents. See `one_off/CLAUDE.md` for inventory.
