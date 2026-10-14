# gitfreeze — design

Status: design approved in-chat (2026-10-09 → 2026-10-14); implemented as v0.1.0.
Audience: public developer tool (GitHub + PyPI). Author: pantha704.

## Product

`gitfreeze` freezes a dormant git project: it pushes everything to the remote,
verifies the push, then removes the committed files from disk while keeping
untracked/ignored/modified files (secrets, envs, local caches) and leaving a
dependency-free `thaw.sh` that restores the folder later.

Goals: safe archive of finished side-projects; reclaim disk; keep secrets
local; zero magic — every deletion recoverable via trash.
Non-goals (v0.1.0): creating remotes (`gh repo create`), auto-PR for protected
branches, regenerable-junk cleanup (`node_modules`), telemetry.

## Freeze flow

1. Detect repo/remote/branch (`rev-parse`, `remote get-url`); refuse
   detached HEAD, no commits, in-progress merge/rebase/bisect.
2. Write `.git/info/exclude` entries for tool artifacts (never pushed).
3. Push preflight: `git push --dry-run` (real auth/permission probe).
4. Dirty tracked files → prompt `commit / keep / abort` (non-tty default:
   abort). `--dirty=commit` stages tracked-only (`add -u`), scans, commits.
5. Scans of outgoing commits: secret-like content (block), tracked
   secret-ish names (warn), files over `max_file_mb` (block), LFS present.
6. Push; re-read remote ref up to 3× and require sha equality — else abort
   with nothing deleted. LFS repos additionally `git lfs push --all`.
7. Plan: purge set = files at the verified sha ∩ currently-clean working
   files. Summary + estimate; confirm (or `-y`).
8. `.git` decision: prompt drop/keep/abort (non-tty default keep); drop gated
   on no stashes and no local-only commits (`--git=drop` refuses otherwise).
9. Write thaw scripts *first*, then two-phase purge: files renamed into
   `.gitfreeze/trash/<utc-ts>/`. Any per-file error → rollback of that file;
   whatever cannot be rolled back stays recoverable via `undo`.
10. Report bytes freed/kept; optional immediate reclamation prompts.

## Safety model

- Only clean-tracked-at-verified-sha files are ever deleted.
- Trash-first, rename-based, crash-safe; `gitfreeze undo` restores;
  `gitfreeze trash empty` reclaims; `--trash=off` needs explicit confirmation.
- Secret scan has no override (strong patterns); rotating commits manually is
  the escape hatch (push first, then freeze).
- Exit codes: 0 ok / 2 preflight / 3 aborted / 4 push-verify / 5 partial purge
  (rolled back) / 6 gate refused.

## Thaw script

`thaw.sh` + `thaw.command` (macOS) + `thaw.cmd` (Windows, locates
Git-for-Windows bash). Needs only git. Embed: remote URL (+github https
fallback), branch, sha, created-at, version.

- `.git` present → `git worktree add` a temp checkout of target (local
  objects, works offline), merge into the folder.
- `.git` absent → clone to temp (branch or `--at sha`), merge, adopt `.git`.
- Merge policy: existing files win; identical files skipped; differing
  incoming copies saved as `<name>.gitfreeze-new`. Re-run is a near no-op.

## CLI

`gitfreeze freeze|status|undo|trash list|empty|config`; aliases `gitfreeze`
and `git-freeze` (so `git freeze` works). Freeze flags: `--dirty`, `--git`,
`--trash`, `--message`, `--force-with-lease`, `--prune-empty-dirs`,
`--dry-run`, `-y`.

## Decisions log

| decision | choice | why |
| --- | --- | --- |
| name | `gitfreeze` (was `gitrunk`) | clean on PyPI/npm/GitHub; `githrun` collision otherwise; freeze/thaw metaphor |
| stack | Python ≥3.11, stdlib-only, PyPI | fastest to a battle-tested safety matrix; pipx/uv story |
| platforms | Linux/macOS/Windows native | `.cmd` shim; 3-OS CI; manual Windows pass pending |
| dirty default | TTY prompt, non-tty abort | predictable for strangers, script-safe |
| `.git` default | TTY prompt, non-tty keep | keep = never destroy local-only history silently |
| trash default | keep (undo window), prompt to empty | data beats disk; reclaim is one command away |
| purge scope | clean tracked at pushed sha | user rule: committed things only, never envs/secrets |
| restore merge | existing wins, dups `*.gitfreeze-new` | non-destructive; re-thaw idempotent |

## Testing

30 tests, no network: local bare repos as remotes, failure injection
(pre-receive reject, stashes, secret fixtures, unicode names), property test
"freeze→thaw ≡ clone@sha + kept files" across generated trees. CI matrix:
ubuntu/macos/windows × Python 3.11/3.13.

## Known limits / v0.2 candidates

- protected branches: clear error, no auto-PR flow
- submodules: left untouched; thaw note only
- case-collision repos: warp not detected (warn candidate)
- content scan capped at 2 MiB/file; per-file subprocess cost on huge first pushes
- Windows thaw UX verified by CI + shim logic; real dual-boot click-test pending
