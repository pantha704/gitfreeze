# gitfreeze

**Freeze dormant projects. Keep your secrets. Thaw with one script.**

`gitfreeze` takes a git project you are done with, pushes everything to its remote,
and then removes the committed files from your disk — leaving behind your
untracked stuff (`.env`, local configs, `node_modules`, notes) and a small
`thaw.sh` script. When you need the code again, you run the script and the
folder is restored.

It is built for the pile of finished side-projects eating your SSD.

```
$ gitfreeze freeze
gitfreeze 0.1.0
  folder: /home/you/projects/old-app
  remote: origin  (git@github.com:you/old-app.git)
  branch: main @ 4f3a2c1d9e8b

plan
  purge 214 committed file(s) — 3.1 MiB
  keep  812.4 MiB of untracked/ignored/dirty files
  .git is 21.3 MiB

what about .git (21.3 MiB)?
  1) drop it too — max space back (history is on the remote; still undoable from trash)
  2) keep it — folder still works offline (git status will look like mass deletions)
  3) abort
  choose [drop/keep/abort]: drop

thaw scripts written: thaw.sh, thaw.command, thaw.cmd
purging…

frozen
  24.4 MiB is staged in .gitfreeze/trash/20261014T181530Z/
  reclaim it any time:  gitfreeze trash empty
  restore everything:  ./thaw.sh   (Windows: double-click thaw.cmd)
  undo this freeze:    gitfreeze undo
```

## Install

```sh
pipx install gitfreeze         # recommended
uv tool install gitfreeze      # or with uv
pip install --user gitfreeze   # or plain pip
```

Needs Python 3.11+ and git. No dependencies. Once installed you also get
`git freeze` as a subcommand (`git-freeze` alias is included).

## Safety model

gitfreeze only ever deletes **files that are clean-tracked at the exact commit
that was just pushed and verified on the remote**:

- push happens first, and the remote ref is re-read and compared byte-for-byte
  against your local commit; a mismatch aborts everything
- untracked, ignored, and modified files are never touched — your `.env` stays
- deletions go into `.gitfreeze/trash/<timestamp>/` (rename-based, crash-safe);
  `gitfreeze undo` puts everything back and `gitfreeze trash empty` reclaims the
  space when you no longer want the undo
- dropping `.git` is gated: refused if you have stashes or local-only commits
- before pushing, outgoing content is scanned for secret-looking material
  (private keys, AWS/GitHub/Slack/OpenAI keys…) and the push is blocked on a
  hit; oversized files that hosts reject are caught before anything is deleted
- thaw never overwrites: if a path exists, the incoming copy is saved next to
  it as `<name>.gitfreeze-new`

Nothing runs silently: in a terminal you get prompts; in scripts you pass
`--dirty=`, `--git=`, `--trash=` and `-y` explicitly.

## The thaw script

`freeze` writes `thaw.sh`, `thaw.command` (macOS double-click) and `thaw.cmd`
(Windows double-click) into the folder. The script needs **nothing but git** —
no gitfreeze install, no Python:

```sh
./thaw.sh            # restore the latest of the frozen branch
./thaw.sh --at SHA   # restore one exact commit
```

If the folder still has its `.git`, thaw restores from local objects (works
offline). Otherwise it clones from the remote into a temp dir and merges,
keeping any local files you had. Existing files always win.

## Commands

| command | what it does |
| --- | --- |
| `gitfreeze freeze` | push, verify, purge committed files, write thaw scripts |
| `gitfreeze status` | repo + trash + thaw state for the folder |
| `gitfreeze undo` | restore the last freeze from trash |
| `gitfreeze trash list` / `trash empty` | inspect / reclaim trash |
| `gitfreeze config` | show effective configuration |

Key `freeze` flags: `--dirty=ask|commit|keep|abort`, `--git=ask|keep|drop`,
`--trash=keep|empty|off`, `--message`, `--force-with-lease`,
`--prune-empty-dirs`, `--dry-run`, `-y/--yes`.

Exit codes: `0` ok · `2` preflight failed (repo/auth/scan) · `3` aborted or
missing confirmation · `4` push/verify failed · `5` purge failed (rolled back) ·
`6` safety gate refused (e.g. dropping `.git` with stashes).

## Configuration

Defaults < global `~/.config/gitfreeze/config.toml` < per-folder
`.gitfreeze.toml` < flags. A folder-local file is kept out of git via
`.git/info/exclude`, and so is everything under `.gitfreeze/`.

```toml
[freeze]
git = "ask"          # ask | keep | drop
dirty = "ask"        # ask | commit | keep | abort
trash = "keep"       # keep | empty | off
max_file_mb = 100    # block pushes containing bigger files
```

## FAQ

**Why not just `rm -rf` and clone later?** Exactly — that is the core of it.
gitfreeze is the safety rails: it verifies the push actually landed, keeps your
secrets and local junk, leaves an undo window, and writes the clone-back script
so future-you does not have to remember anything.

**Will it free space from `node_modules`?** No — only *committed* files are
purged, and that stuff is normally ignored. gitfreeze is about archiving the
repo, not cleaning build junk. Pair it with your favourite cache cleaner.

**What does keeping `.git` buy me?** Offline restore and full local history.
The trade: less space reclaimed, and `git status` will show the purged files as
deleted until you thaw (that is expected — `git checkout .` brings them back).

**Can I re-run a thaw?** Yes. Files that already match are left alone; anything
genuinely different keeps your local version and drops the incoming copy next
to it as `*.gitfreeze-new`.

**Windows?** Yes — native. `thaw.cmd` finds Git for Windows' bash. Everything
else is pure Python + git CLI.

## License

MIT
