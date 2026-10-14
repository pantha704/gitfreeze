"""The freeze command: push, verify, purge committed files, keep everything else."""

from __future__ import annotations

import os
import time
from pathlib import Path

from . import __version__
from . import config as cfg
from . import fsops, gitcmd, preflight, purge as purge_mod, scriptgen, secretscan, state, trash, ui
from .errors import Aborted, GateError, PartialPurgeError, PreflightError, VerifyError


def cmd_freeze(args) -> int:
    root = Path(args.path or ".").resolve()

    if state.read(root):
        raise PreflightError(
            "a previous operation looks interrupted (.gitfreeze/state.json present) — "
            "run `gitfreeze status`, then `gitfreeze undo` or `gitfreeze trash empty`"
        )

    facts = preflight.detect(root, args.remote or "origin", args.branch)
    root = facts.root
    conf = cfg.load(root)
    tty = ui.is_tty()

    ui.say(ui.bold(f"gitfreeze {__version__}"))
    ui.say(f"  folder: {root}")
    ui.say(f"  remote: {facts.remote}  ({facts.remote_url})")
    ui.say(f"  branch: {facts.branch} @ {facts.head_sha[:12]}")

    probe_error = preflight.push_probe(root, facts, force=args.force_with_lease, noninteractive=not tty)
    if probe_error:
        raise PreflightError("push preflight failed:\n" + probe_error)

    if not args.dry_run:
        preflight.ensure_excludes(root, facts.git_dir)

    dirty, untracked = preflight.dirty_sets(root)

    # ---------------- dry run: report only ----------------
    if args.dry_run:
        ui.say(ui.bold("dry-run — nothing will be touched"))
        if dirty:
            mode = args.dirty if args.dirty is not None else conf["freeze.dirty"]
            ui.say(f"  {len(dirty)} modified tracked file(s); --dirty mode would apply: {mode}")
        _run_scans(root, facts, conf, interactive=False)
        purge_paths, purge_bytes, git_bytes, kept_bytes = _plan(root, facts, dirty)
        _print_plan(purge_paths, purge_bytes, kept_bytes, git_bytes, untracked)
        git_mode = args.git if args.git is not None else conf["freeze.git"]
        if git_mode == "drop" and (root / ".git").exists():
            try:
                _drop_git_gates(root)
                ui.say("  .git: would be dropped (gates pass)")
            except GateError as exc:
                ui.say(f"  .git: drop would be refused — {exc}")
        return 0

    # ---------------- dirty handling ----------------
    dirty_mode = args.dirty if args.dirty is not None else conf["freeze.dirty"]
    if dirty:
        if dirty_mode == "ask":
            if tty:
                shown = sorted(dirty)
                ui.say(f"modified/added tracked files ({len(shown)}):")
                for name in shown[:15]:
                    ui.say(f"  {name}")
                if len(shown) > 15:
                    ui.say(f"  … and {len(shown) - 15} more")
                dirty_mode = ui.ask_choice(
                    "what should freeze do with them?",
                    [
                        ("commit", "commit them (tracked files only) and push"),
                        ("keep", "keep them on disk, freeze everything else"),
                        ("abort", "abort"),
                    ],
                    default="abort",
                )
                if ui.ask_yes_no("remember this choice for this folder?"):
                    cfg.set_local(root, "freeze.dirty", dirty_mode)
            else:
                dirty_mode = "abort"
        if dirty_mode == "abort":
            listing = "\n  ".join(sorted(dirty)[:20])
            raise Aborted(
                f"{len(dirty)} modified tracked file(s):\n  {listing}\n"
                "commit them first, or pass --dirty=commit / --dirty=keep"
            )
        if dirty_mode == "commit":
            _commit_tracked(root, dirty, untracked, args, conf)
            facts = preflight.detect(root, facts.remote, branch=facts.branch)
            dirty, untracked = preflight.dirty_sets(root)
    elif dirty_mode == "commit":
        ui.say("no tracked changes to commit")

    # ---------------- scans ----------------
    _run_scans(root, facts, conf, interactive=tty and not args.yes)

    lfs = secretscan.detect_lfs(root)

    # ---------------- push ----------------
    ui.say("pushing…")
    push_args = ["push"]
    if args.force_with_lease:
        push_args.append("--force-with-lease")
    push_args += [facts.remote, f"HEAD:refs/heads/{facts.branch}"]
    proc = gitcmd.run(root, *push_args, check=False, noninteractive=not tty)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
        hint = ""
        low = err.lower()
        if "protected" in low or "declined" in low or "pre-receive" in low:
            hint = "\n(if this branch is protected and needs a pull request, push a separate branch and open a PR yourself)"
        raise VerifyError(f"push failed:\n{err[-1500:]}{hint}")

    verified = False
    for _ in range(3):
        reachable, sha, _err = preflight.remote_sha(root, facts.remote, facts.branch, noninteractive=True)
        if reachable and sha == facts.head_sha:
            verified = True
            break
        time.sleep(1)
    if not verified:
        raise VerifyError(f"remote ref did not reach {facts.head_sha[:12]} — aborting before any deletion")
    ui.say("push verified ✓")

    if lfs:
        proc = gitcmd.run(root, "lfs", "push", "--all", facts.remote, facts.branch, check=False, noninteractive=not tty)
        if proc.returncode != 0:
            raise VerifyError("git lfs push --all failed — refusing to purge")

    # ---------------- plan ----------------
    purge_paths, purge_bytes, git_bytes, kept_bytes = _plan(root, facts, dirty)
    ui.say("")
    _print_plan(purge_paths, purge_bytes, kept_bytes, git_bytes, untracked)

    if not args.yes:
        if not ui.ask_yes_no(
            f"proceed? {len(purge_paths)} file(s) move into .gitfreeze trash (undoable with `gitfreeze undo`)",
            default=False,
        ):
            raise Aborted("declined")

    # ---------------- .git decision ----------------
    has_git = (root / ".git").exists()
    git_mode = args.git if args.git is not None else conf["freeze.git"]
    if not has_git:
        git_mode = "keep"
    elif git_mode == "ask":
        if tty:
            git_mode = ui.ask_choice(
                f"what about .git ({ui.human_bytes(git_bytes)})?",
                [
                    ("drop", "drop it too — max space back (history is on the remote; still undoable from trash)"),
                    ("keep", "keep it — folder still works offline (git status will look like mass deletions)"),
                    ("abort", "abort"),
                ],
                default="keep",
            )
            if ui.ask_yes_no("remember this choice for this folder?"):
                cfg.set_local(root, "freeze.git", git_mode)
        else:
            git_mode = "keep"
    if git_mode == "abort":
        raise Aborted("declined")
    if git_mode == "drop":
        _drop_git_gates(root)

    trash_mode = args.trash if args.trash is not None else conf["freeze.trash"]
    if trash_mode == "off" and not args.yes:
        if not (tty and ui.ask_yes_no("--trash=off permanently deletes — no undo. really do that?", default=False)):
            raise Aborted("refusing permanent delete without confirmation (pass --yes to allow, or use --trash=keep)")

    prune = bool(args.prune_empty_dirs or conf["freeze.prune_empty_dirs"])

    # ---------------- scripts first, then purge ----------------
    record_meta = {
        "created": time.time(),
        "root": str(root),
        "remote": facts.remote,
        "remote_url": facts.remote_url,
        "branch": facts.branch,
        "sha": facts.head_sha,
        "gitfreeze_version": __version__,
        "kept_dirty": sorted(dirty),
        "kept_untracked_count": len(untracked),
    }
    scripts = scriptgen.write_thaw_scripts(root, record_meta)
    ui.say("thaw scripts written: " + ", ".join(p.name for p in scripts))

    state.begin(root, "freeze", phase="purging")
    ui.say("purging…")

    if trash_mode == "off":
        errors = purge_mod.delete_paths(root, purge_paths)
        if errors:
            state.end(root)
            raise PartialPurgeError(errors)
        if git_mode == "drop":
            try:
                fsops.rmtree(root / ".git")
            except OSError as exc:
                state.end(root)
                raise PartialPurgeError([(".git", str(exc))]) from exc
        if prune:
            fsops.prune_empty_dirs(root)
        state.log(root, "freeze", mode="off", files=len(purge_paths), bytes=purge_bytes, git=git_mode)
        state.end(root)
        freed = purge_bytes + (git_bytes if git_mode == "drop" else 0)
        ui.say("")
        ui.say(ui.bold(f"frozen — {ui.human_bytes(freed)} freed (permanent: --trash=off)"))
        ui.say("  restore everything:  ./thaw.sh")
        return 0

    record = trash.new_record(root, record_meta)
    state.update(root, record=record.name, phase="trash")
    remaining, purge_errors, rolled_back = purge_mod.trash_paths(root, purge_paths, record / "files")
    if purge_errors:
        manifest = trash.load(record)
        manifest["files"] = remaining
        manifest["git_dropped"] = False
        manifest["status"] = "complete" if remaining else "rolled_back"
        manifest["errors"] = [f"{p}: {e}" for p, e in purge_errors[:50]]
        trash.save(record, manifest)
        if not remaining:
            fsops.rmtree(record, ignore_errors=True)
        state.end(root)
        raise PartialPurgeError(purge_errors, rolled_back=rolled_back)
    moved = remaining

    if git_mode == "drop":
        state.update(root, phase="dot-git")
        os.replace(root / ".git", record / "dot-git")

    manifest = trash.load(record)
    manifest["files"] = moved
    manifest["git_dropped"] = git_mode == "drop"
    manifest["status"] = "complete"
    trash.save(record, manifest)

    if prune:
        fsops.prune_empty_dirs(root)

    state.log(
        root,
        "freeze",
        mode=trash_mode,
        files=len(moved),
        bytes=purge_bytes,
        git=git_mode,
        record=record.name,
    )
    state.end(root)

    staged = purge_bytes + (git_bytes if git_mode == "drop" else 0)
    ui.say("")
    ui.say(ui.bold("frozen"))
    if trash_mode == "empty":
        _removed, reclaimed = trash.empty(root, record_id=record.name)
        ui.say(f"  freed {ui.human_bytes(reclaimed)}")
    else:
        ui.say(f"  {ui.human_bytes(staged)} is staged in .gitfreeze/trash/{record.name}/")
        ui.say("  reclaim it any time:  gitfreeze trash empty")
        if tty and ui.ask_yes_no(f"empty the trash now and reclaim {ui.human_bytes(staged)}?", default=False):
            _removed, reclaimed = trash.empty(root, record_id=record.name)
            ui.say(f"  freed {ui.human_bytes(reclaimed)}")
    ui.say("  restore everything:  ./thaw.sh   (Windows: double-click thaw.cmd)")
    ui.say("  undo this freeze:    gitfreeze undo")
    return 0


# ---------------------------------------------------------------------------


def _commit_tracked(root, dirty: set[str], untracked: set[str], args, conf) -> None:
    names = sorted(dirty)
    ui.say(f"committing {len(names)} tracked change(s):")
    for name in names[:20]:
        ui.say(f"  {name}")
    if len(names) > 20:
        ui.say(f"  … and {len(names) - 20} more")

    hits = secretscan.scan_committable_content(root, names)
    if hits:
        raise PreflightError(
            "secret-like content in files about to be committed:\n  "
            + "\n  ".join(hits)
            + "\n(review and remove before freezing)"
        )
    max_mb = int(conf["freeze.max_file_mb"])
    for name in names:
        try:
            size = os.lstat(root / name).st_size
        except OSError:
            continue
        if size > max_mb * 1024 * 1024:
            raise PreflightError(
                f"{name} is {ui.human_bytes(size)} (> {max_mb} MiB) — hosts like GitHub reject files over that"
            )
    if untracked:
        ui.say(f"note: {len(untracked)} untracked file(s) are not committed (they stay on disk)")
    gitcmd.run(root, "add", "-u")
    message = args.message or conf["freeze.message"] or f"gitfreeze: freeze {time.strftime('%Y-%m-%d %H:%M')}"
    gitcmd.run(root, "commit", "-m", message)
    ui.say("committed " + gitcmd.out(root, "rev-parse", "--short", "HEAD"))


def _run_scans(root, facts, conf, interactive: bool) -> None:
    reachable, rsha, _err = preflight.remote_sha(root, facts.remote, facts.branch, noninteractive=True)
    out_paths = secretscan.outgoing_paths(root, rsha if reachable else None)

    blockers, unscanned = secretscan.scan_outgoing_content(root, out_paths)
    if blockers:
        raise PreflightError(
            "secret-like content in commits that would be pushed:\n  "
            + "\n  ".join(blockers)
            + "\n(remove or rotate it; nothing was deleted)"
        )
    if unscanned:
        ui.warn("not content-scanned (>2 MiB): " + ", ".join(unscanned[:5]))

    name_warns = secretscan.scan_tracked_names(root)
    if name_warns:
        ui.warn("tracked files with secret-ish names: " + ", ".join(name_warns[:10]))
        if interactive and not ui.ask_yes_no("continue anyway?", default=False):
            raise Aborted("declined")

    max_mb = int(conf["freeze.max_file_mb"])
    warn_mb = int(conf["freeze.warn_file_mb"])
    sizes = preflight.tree_sizes(root, facts.head_sha)
    too_big = [(p, sizes.get(p, 0)) for p in out_paths if sizes.get(p, 0) > max_mb * 1024 * 1024]
    if too_big:
        listing = ", ".join(f"{p} ({ui.human_bytes(s)})" for p, s in too_big[:5])
        raise PreflightError(f"file(s) over {max_mb} MiB would be pushed and rejected: {listing}")
    warn_big = sorted(
        p for p in out_paths if warn_mb * 1024 * 1024 < sizes.get(p, 0) <= max_mb * 1024 * 1024
    )
    if warn_big:
        ui.warn("large files (>{} MiB): {}".format(warn_mb, ", ".join(warn_big[:5])))
        if interactive and not ui.ask_yes_no("continue anyway?", default=False):
            raise Aborted("declined")


def _plan(root, facts, dirty: set[str]):
    tree = preflight.ls_tree_files(root, facts.head_sha)
    present = [p for p in tree if fsops.lexists(root / p)]
    purge_paths = sorted(set(present) - dirty)
    purge_bytes = 0
    for p in purge_paths:
        try:
            purge_bytes += os.lstat(root / p).st_size
        except OSError:
            pass
    git_bytes = fsops.dir_size(root / ".git") if (root / ".git").exists() else 0
    total_bytes = fsops.dir_size(root, skip_top={".git", ".gitfreeze"})
    kept_bytes = max(0, total_bytes - purge_bytes)
    return purge_paths, purge_bytes, git_bytes, kept_bytes


def _print_plan(purge_paths, purge_bytes, kept_bytes, git_bytes, untracked) -> None:
    ui.say(ui.bold("plan"))
    ui.say(f"  purge {len(purge_paths)} committed file(s) — {ui.human_bytes(purge_bytes)}")
    ui.say(f"  keep  {ui.human_bytes(kept_bytes)} of untracked/ignored/dirty files")
    if untracked:
        sample = ", ".join(sorted(untracked)[:5])
        ui.say(f"  {len(untracked)} untracked file(s) stay on disk (e.g. {sample})")
    if git_bytes:
        ui.say(f"  .git is {ui.human_bytes(git_bytes)}")


def _drop_git_gates(root) -> None:
    info = preflight.unpushed(root)
    if info["stashes"]:
        raise GateError(
            f"cannot drop .git: {len(info['stashes'])} stash(es) exist and stashes live only in .git.\n"
            "  → use --git=keep, or drop your stashes first"
        )
    if info["unpushed"]:
        shown = "\n  ".join(info["unpushed"][:10])
        raise GateError(
            "cannot drop .git: local-only commits exist (not reachable from any remote):\n  "
            + shown
            + "\n  → push those refs, or use --git=keep"
        )
