Title: [BUG] `/resume` writes entries to wrong JSONL file — single-process, no concurrency required

---

### Preflight Checklist

- [x] I have searched [existing issues](https://github.com/anthropics/claude-code/issues?q=is%3Aissue%20state%3Aopen%20label%3Abug) and this hasn't been reported yet
- [x] This is a single bug report (please file separate reports for different bugs)
- [x] I am using the latest version of Claude Code

### What's Wrong?

After using `/resume` to switch between sessions within the TUI, new messages are appended to the **previously active session's JSONL file** instead of the newly resumed session's file. The entries carry the correct `sessionId` but land in the wrong file, corrupting the target session and orphaning the new conversation data.

This is a **single-process, single-terminal** bug. No concurrent sessions, no `/compact`, no `/rename`, no `/fork` required.

### What Should Happen?

After `/resume` switches to a different session, all new entries should be written to that session's own JSONL file.

### Steps to Reproduce

1. Create a fresh project directory
2. Run `claude`, send at least one message, exit
3. Run `claude` again (new session), send at least one message, exit
4. Run `claude --resume`, pick either session
5. Send a message (goes to the correct file)
6. `/resume` and pick the **other** session
7. Send a message — **it goes to the wrong file**

### Observed Behavior

After step 6-7:

- The message sent in step 7 appears in the **step-4 session's JSONL file**, not the resumed session's file
- The entry has the correct `sessionId` (the resumed session) but is appended to the wrong file
- `file-history-snapshot` entries referencing the resumed session's messages leak into the wrong file **before** the message entries do — snapshots are the first thing to contaminate
- `--resume` (step 4) creates a stub `.jsonl` file containing a single `file-history-snapshot` as a side effect

### Evidence

Slim view of a contaminated file after the repro (`7a0de4b4` is the victim, `8eb76498` is the resumed session whose entries land in the wrong file):

```
line  type                    sessionId   uuid          parentUuid
1     file-history-snapshot   None        None          None          # own snapshot
2     user                    7a0de4b4    920291fa...   None          # own message
3     assistant               7a0de4b4    9f5dcfbe...   920291fa...   # own message
4     file-history-snapshot   None        None          None          # own snapshot
5     user                    7a0de4b4    38a1f5b4...   9f5dcfbe...   # own message
6     assistant               7a0de4b4    1c7008af...   38a1f5b4...   # own message
7     file-history-snapshot   None        None          None          # references 8eb76498's message!
8     file-history-snapshot   None        None          None          # references 8eb76498's message!
9     user                    8eb76498    1217cf63...   c8f268f1...   # WRONG FILE
10    assistant               8eb76498    693d0391...   1217cf63...   # WRONG FILE
```

Lines 9-10 have `sessionId=8eb76498` but are in `7a0de4b4`'s file. The `parentUuid` on line 9 (`c8f268f1`) only exists in `8eb76498`'s own file, creating a broken chain.

The `file-history-snapshot` entries at lines 7-8 have `messageId` fields referencing UUIDs from `8eb76498`'s session — the write target shifted to the wrong file at the snapshot level before the first message entry.

### Impact

- **Broken `parentUuid` chains**: The resumed session's messages have parents that only exist in another file. The chain-walking code can't find them, so the conversation appears blank on resume.
- **Orphaned data**: The contaminating entries may not exist in their own session's file, so the conversation data is only recoverable by manually extracting it from the wrong file.
- **Title corruption**: When this combines with `/rename` or the auto-titler, `custom-title` entries for the wrong session get written to the victim file, causing the session picker to display incorrect names (see #27202).

### Relationship to Existing Issues

- **#26964** (canonical cross-session contamination): Same symptom, but that issue describes concurrent multi-process contamination. This repro is single-process, sequential, and requires only `/resume`.
- **#27202** (`/rename` applies title to wrong session): A downstream consequence — once entries are in the wrong file, the title scanner picks up the wrong `custom-title`.
- **#29342** (session transcript writes to wrong JSONL file): Closed as dup of #26964. Describes the same write-target confusion but couldn't identify the trigger.

This may share a root cause with #26964 (the file write target / file descriptor not being updated), but the trigger mechanism is distinct and much easier to reproduce.

### Claude Code Version

2.1.68

### Platform

Anthropic API (also reproduced via Docker)

### Operating System

macOS (Darwin 24.6.0), also reproduced on Linux (Docker)

### Terminal/Shell

zsh

### Claude Model

Opus

### Additional Information

**Key observation about `file-history-snapshot` entries**: These entries carry no `sessionId`, no `slug`, and no `timestamp` — they are completely anonymous. They are also the first entries to leak into the wrong file (before any message entries), which suggests the contamination starts at the snapshot/save layer, not the message-writing layer. The only way to attribute a snapshot to a session is by looking up which session owns the `messageId` it references.
