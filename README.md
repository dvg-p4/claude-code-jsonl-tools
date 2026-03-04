# claude-code-jsonl-tools

Diagnostic and repair tools for [Claude Code](https://claude.ai/claude-code) session JSONL cross-contamination bugs, where entries get written to the wrong session file.

See [CLAUDE.md](CLAUDE.md) for full bug documentation, reproduction steps, and repair strategies.

Related issues: [#30802](https://github.com/anthropics/claude-code/issues/30802), [#26964](https://github.com/anthropics/claude-code/issues/26964), [#27202](https://github.com/anthropics/claude-code/issues/27202)

## Tools

- **`diagnose.py`** — Analyzes JSONL files for foreign entries, broken `parentUuid` chains, duplicate UUIDs, snapshot attribution shifts, and orphaned data. Reconstructs a contamination timeline when given multiple files.

  ```
  python3 diagnose.py FILE1.jsonl [FILE2.jsonl ...]
  ```

- **`slim.py`** — Prints a tab-separated summary of JSONL entries for quick inspection. Designed for `sort` and `column -ts$'\t'`.

  ```
  python3 slim.py FILE1.jsonl [FILE2.jsonl ...]
  ```
