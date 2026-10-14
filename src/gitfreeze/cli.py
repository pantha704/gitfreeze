"""Command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__, config as cfg, fsops, preflight, state, trash, ui
from .errors import Aborted, GitFreezeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitfreeze",
        description="Freeze a dormant git project: push, purge committed files (secrets stay on disk), thaw with one script.",
    )
    parser.add_argument("--version", action="version", version=f"gitfreeze {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("freeze", help="push, then purge committed files from this folder")
    p.add_argument("path", nargs="?", default=".", help="folder inside the repository (default: current directory)")
    p.add_argument("--remote", default=None, help="remote name (default: origin)")
    p.add_argument("--branch", default=None, help="branch to push (default: the current branch)")
    p.add_argument(
        "--dirty",
        choices=["ask", "commit", "keep", "abort"],
        default=None,
        help="what to do with modified tracked files (default: ask in a terminal, abort otherwise)",
    )
    p.add_argument(
        "--git",
        choices=["ask", "keep", "drop"],
        default=None,
        help="what to do with the .git folder (default: ask in a terminal, keep otherwise)",
    )
    p.add_argument(
        "--trash",
        choices=["keep", "empty", "off"],
        default=None,
        help="trash behavior: keep = undoable, reclaim later (default); empty = reclaim now; off = permanent delete",
    )
    p.add_argument("--message", default=None, help="commit message used with --dirty=commit")
    p.add_argument("--force-with-lease", action="store_true", help="push with --force-with-lease")
    p.add_argument("--prune-empty-dirs", action="store_true", help="remove directories the purge leaves empty")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompts (needed in scripts)")
    p.add_argument("--dry-run", action="store_true", help="show what would happen; change nothing")

    s = sub.add_parser("status", help="show freeze/trash state for a folder")
    s.add_argument("path", nargs="?", default=".")

    u = sub.add_parser("undo", help="restore the last freeze from trash")
    u.add_argument("path", nargs="?", default=".")
    u.add_argument("--id", default=None, help="specific record id (see: gitfreeze trash list)")

    t = sub.add_parser("trash", help="inspect or empty trash records")
    t.add_argument("action", choices=["list", "empty"])
    t.add_argument("path", nargs="?", default=".")
    t.add_argument("--id", default=None)
    t.add_argument("-y", "--yes", action="store_true", help="skip confirmation")

    c = sub.add_parser("config", help="show effective configuration")
    c.add_argument("path", nargs="?", default=".")

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "freeze":
            from .freeze import cmd_freeze

            return cmd_freeze(args)
        if args.cmd == "status":
            return cmd_status(args)
        if args.cmd == "undo":
            return cmd_undo(args)
        if args.cmd == "trash":
            return cmd_trash(args)
        if args.cmd == "config":
            return cmd_config(args)
        build_parser().print_help()
        return 0
    except GitFreezeError as exc:
        ui.error(str(exc))
        return exc.exit_code
    except KeyboardInterrupt:
        ui.error("interrupted")
        return 130


def cmd_status(args) -> int:
    root = Path(args.path).resolve()
    lines: list[str] = []
    try:
        facts = preflight.detect(root)
        dirty, untracked = preflight.dirty_sets(root)
        reachable, sha, _err = preflight.remote_sha(root, facts.remote, facts.branch)
        lines.append(f"repo:    {facts.root}")
        lines.append(f"remote:  {facts.remote}  {facts.remote_url}")
        lines.append(f"branch:  {facts.branch} @ {facts.head_sha[:12]}")
        lines.append(f"dirty:   {len(dirty)} modified, {len(untracked)} untracked")
        lines.append(
            "remote:  "
            + (f"{sha[:12]} ({'in sync' if sha == facts.head_sha else 'out of sync'})" if sha else "branch not on remote yet")
        )
    except GitFreezeError as exc:
        lines.append(str(exc))
    gz = root / ".gitfreeze"
    if gz.exists():
        recs = trash.records(root)
        if recs:
            lines.append("trash records:")
            for rec in recs:
                d = trash.record_dir(root, rec["id"])
                size = fsops.dir_size(d)
                flags = rec.get("status", "?")
                if rec.get("undone"):
                    flags += ", undone"
                lines.append(
                    f"  {rec['id']}: {len(rec.get('files', []))} files, {ui.human_bytes(size)}, "
                    f"git_dropped={bool(rec.get('git_dropped'))}, {flags}"
                )
        if state.read(root):
            lines.append("!! an interrupted operation marker is present (.gitfreeze/state.json)")
        if (root / "thaw.sh").exists():
            lines.append("thaw script present — run ./thaw.sh to restore this folder")
    else:
        lines.append("no .gitfreeze data found here")
    ui.say("\n".join(lines))
    return 0


def cmd_undo(args) -> int:
    root = Path(args.path).resolve()
    record_id = trash.undo(root, args.id)
    ui.say(f"undone: {record_id} — files restored")
    state.log(root, "undo", record=record_id)
    return 0


def cmd_trash(args) -> int:
    root = Path(args.path).resolve()
    if args.action == "list":
        recs = trash.records(root)
        if not recs:
            ui.say("trash is empty")
            return 0
        for rec in recs:
            d = trash.record_dir(root, rec["id"])
            size = fsops.dir_size(d)
            extra = " undone" if rec.get("undone") else ""
            ui.say(
                f"{rec['id']}  {len(rec.get('files', []))} files  {ui.human_bytes(size)}  "
                f"git_dropped={bool(rec.get('git_dropped'))}  status={rec.get('status')}{extra}"
            )
        return 0
    if not args.yes and not ui.ask_yes_no("permanently delete trash records (undo will stop working)?", default=False):
        raise Aborted("declined")
    removed, reclaimed = trash.empty(root, record_id=args.id)
    ui.say(f"removed {removed} record(s), reclaimed {ui.human_bytes(reclaimed)}")
    state.log(root, "trash.empty", records=removed, bytes=reclaimed)
    return 0


def cmd_config(args) -> int:
    root = Path(args.path).resolve()
    conf = cfg.load(root)
    ui.say(f"global: {cfg.global_path()}")
    ui.say(f"local:  {cfg.local_path(root)}")
    for key in sorted(conf):
        ui.say(f"  {key} = {conf[key]!r}")
    return 0
