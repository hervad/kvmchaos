"""Interactive confirmation helper.

Provides a single `confirm` function used by the CLI before any
destructive or irreversible operation.
"""

from __future__ import annotations

import sys


def confirm(prompt: str, *, assume_yes: bool) -> bool:
    """Ask the user to confirm an action before proceeding.

    Args:
        prompt: Human-readable question to display before the [y/N] hint.
        assume_yes: If True, skip the prompt and return True immediately.
            Intended for scripted use via `--yes`.

    Returns:
        True if the user typed `y` or `yes` (any case), False otherwise.
        Empty or unrecognised input defaults to False.
    """
    if assume_yes:
        return True
    print(f"{prompt} [y/N] ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    return answer in {"y", "yes"}
