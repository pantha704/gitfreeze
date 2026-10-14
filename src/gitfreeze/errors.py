"""Exit-code mapped exception hierarchy."""

from __future__ import annotations

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PREFLIGHT = 2
EXIT_ABORTED = 3
EXIT_VERIFY = 4
EXIT_PARTIAL = 5
EXIT_GATE = 6


class GitFreezeError(Exception):
    """Base error; carries the process exit code."""

    exit_code = EXIT_ERROR


class PreflightError(GitFreezeError):
    """Repo state / auth / scans failed; nothing was changed."""

    exit_code = EXIT_PREFLIGHT


class Aborted(GitFreezeError):
    """User declined, or non-interactive run needs an explicit flag."""

    exit_code = EXIT_ABORTED


class VerifyError(GitFreezeError):
    """Push or verification against the remote failed; nothing was deleted."""

    exit_code = EXIT_VERIFY


class PartialPurgeError(GitFreezeError):
    """Purge failed part-way; attempted rollback."""

    exit_code = EXIT_PARTIAL

    def __init__(self, errors, rolled_back: int = 0):
        lines = [f"{p}: {e}" for p, e in errors[:20]]
        if len(errors) > 20:
            lines.append(f"... and {len(errors) - 20} more")
        msg = "purge failed for:\n  " + "\n  ".join(lines)
        if rolled_back:
            msg += f"\nrolled back {rolled_back} already-trashed file(s)"
        super().__init__(msg)


class GateError(GitFreezeError):
    """A safety gate refused the operation (e.g. dropping .git with local-only work)."""

    exit_code = EXIT_GATE
