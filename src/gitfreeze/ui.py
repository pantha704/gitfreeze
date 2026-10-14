"""Terminal output and prompts. All prompts degrade safely when not on a TTY."""

from __future__ import annotations

import os
import sys

from .errors import Aborted


def is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def bold(s: str) -> str:
    return f"\x1b[1m{s}\x1b[0m" if _color() else s


def dim(s: str) -> str:
    return f"\x1b[2m{s}\x1b[0m" if _color() else s


def say(*parts) -> None:
    print(*parts)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def human_bytes(n: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    v = float(n)
    for unit in units:
        if v < 1024 or unit == units[-1]:
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{n} B"


def ask_choice(title: str, options, default: str | None = None) -> str:
    """options: list of (key, label). Returns the chosen key.

    Non-interactive: returns default, or raises Aborted when there is none.
    """
    say(title)
    for i, (key, label) in enumerate(options, 1):
        say(f"  {i}) {label}")
    if not is_tty():
        if default is None:
            raise Aborted("no terminal available for a prompt; pass an explicit flag")
        return default
    keys = "/".join(k for k, _ in options)
    while True:
        try:
            raw = input(f"  choose [{keys}]: ").strip().lower()
        except EOFError:
            raw = ""
        if not raw and default is not None:
            return default
        for key, _ in options:
            if raw == key.lower():
                return key
        say("  ? try again")


def ask_yes_no(question: str, default: bool = False) -> bool:
    if not is_tty():
        return default
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            raw = input(question + suffix + " ").strip().lower()
        except EOFError:
            return default
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        say("  ? y or n")
