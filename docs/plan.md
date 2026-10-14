# Implementation plan / status

## Milestones

- **M0 — spec**: design approved and recorded in `docs/specs/2026-10-14-gitfreeze-design.md` ✅
- **M1 — freeze core**: detection, preflight (push probe), dirty handling,
  push + sha verify, plan, trash purge, undo, thaw script generation ✅
- **M2 — safety**: secret scan, big-file gate, LFS upload, `.git` drop gates,
  crash state markers, rollback semantics ✅
- **M3 — restore**: worktree (offline) + clone merge paths, collision policy,
  `--at sha`, Windows/macOS shims ✅
- **M4 — tests/CI**: 30 tests (bare-repo remotes, failure injection, roundtrip
  property), 3-OS × py3.11/3.13 workflow ✅ (CI green pending first push)
- **M5 — release**: README/docs, MIT, PyPI publish via trusted publishing,
  GitHub release with wheel/sdist ⏳ (repo + release; PyPI needs account link)

## Next actions

1. Push to `github.com/pantha704/gitfreeze`; confirm CI matrix green.
2. PyPI one-time setup (see `RELEASING.md`), then cut `v0.1.0+` publishes.
3. Windows manual pass on the dual-boot (double-click `thaw.cmd` flow).
4. Backlog: case-collision warning, submodule notes in thaw, prune `--at`
   detached-HEAD note, `gitfreeze restore` convenience command.
