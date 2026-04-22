"""Thin subprocess wrapper for tc (iproute2) qdisc commands.

All functions that mutate qdisc state require root or CAP_NET_ADMIN on
the host. A non-zero exit from tc raises RuntimeError with the stderr output.
"""

from __future__ import annotations

import subprocess


def add_netem_delay(dev: str, delay_ms: int) -> None:
    """Add or replace a netem qdisc with a fixed delay on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        delay_ms: One-way delay in milliseconds.

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "delay", f"{delay_ms}ms"])


def del_root_qdisc(dev: str) -> None:
    """Remove the root qdisc from a network device, restoring the kernel default.

    Args:
        dev: Host network device name.

    Raises:
        RuntimeError: If tc exits non-zero.
    """
    _run(["tc", "qdisc", "del", "dev", dev, "root"])


def show_qdisc(dev: str) -> str:
    """Return the output of ``tc qdisc show dev <dev>``.

    Never raises — returns empty string on failure so callers can
    inspect without catching exceptions.

    Args:
        dev: Host network device name.

    Returns:
        Raw stdout from tc, or empty string if tc fails.
    """
    result = subprocess.run(
        ["tc", "qdisc", "show", "dev", dev],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _run(cmd: list[str]) -> None:
    """Run a tc command, raising RuntimeError on non-zero exit.

    Args:
        cmd: Full command list including ``'tc'`` as first element.

    Raises:
        RuntimeError: If the command exits non-zero.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"tc command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
