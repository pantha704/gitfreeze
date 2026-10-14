# Changelog

## 0.1.0 — 2026-10-14

Initial release.

- `gitfreeze freeze` — push preflight (`--dry-run` probe), dirty handling
  (`commit`/`keep`/`abort`), outgoing secret scan, oversized-file gate, push +
  remote sha verification, two-phase trash purge, `.git` keep/drop with
  safety gates, thaw script generation, immediate or deferred reclamation.
- `gitfreeze undo` / `trash list|empty` / `status` / `config`.
- Thaw scripts (`thaw.sh`, `thaw.command`, `thaw.cmd`) that restore with only
  git: offline restore from local `.git` via worktree, clone+merge otherwise,
  existing files always win, differing incoming copies saved as
  `*.gitfreeze-new`.
- Works on Linux, macOS and Windows (Python ≥3.11, no dependencies).
