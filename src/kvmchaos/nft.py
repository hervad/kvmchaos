"""Thin subprocess wrapper for nft (nftables) commands.

All functions that mutate nftables state require root or CAP_NET_ADMIN on
the host. A non-zero exit from nft raises RuntimeError with the stderr output.

Each partition uses a dedicated table named ``kvmchaos-<dev>`` so multiple
concurrent partitions on different tap devices do not interfere, and cleanup
is a single table delete.
"""

from __future__ import annotations

import subprocess

_TABLE_FAMILY = "inet"
_CHAIN_NAME = "forward"
_CHAIN_PRIORITY = -1  # runs before firewalld's filter+10 chains


def _table_name(dev: str) -> str:
    return f"kvmchaos-{dev}"


def add_partition(dev: str) -> None:
    """Create an nftables table that drops all traffic on a tap device.

    Creates a dedicated ``inet kvmchaos-<dev>`` table with a forward hook
    at priority -1 (before firewalld). Two rules drop all packets where the
    tap device is either ingress or egress.

    Args:
        dev: Host tap device name (e.g. ``'vnet0'``).

    Raises:
        RuntimeError: If any nft command exits non-zero.
    """
    table = _table_name(dev)
    _run(["nft", "add", "table", _TABLE_FAMILY, table])
    _run(
        [
            "nft",
            "add",
            "chain",
            _TABLE_FAMILY,
            table,
            _CHAIN_NAME,
            f"{{ type filter hook forward priority {_CHAIN_PRIORITY}; policy accept; }}",
        ]
    )
    _run(["nft", "add", "rule", _TABLE_FAMILY, table, _CHAIN_NAME, "iifname", dev, "drop"])
    _run(["nft", "add", "rule", _TABLE_FAMILY, table, _CHAIN_NAME, "oifname", dev, "drop"])


def del_partition(dev: str) -> None:
    """Delete the kvmchaos partition table for a tap device.

    Removing the table atomically removes all chains and rules within it.
    Safe to call even if the table does not exist (nft exits 0 in that case
    on modern kernels; if it fails we suppress the error since the desired
    state — no table — is already achieved).

    Args:
        dev: Host tap device name.
    """
    table = _table_name(dev)
    result = subprocess.run(
        ["nft", "delete", "table", _TABLE_FAMILY, table],
        capture_output=True,
        text=True,
    )
    # Ignore "No such file" errors — table already absent means revert is done.
    if result.returncode != 0 and "No such file" not in result.stderr:
        raise RuntimeError(
            f"nft command failed: nft delete table {_TABLE_FAMILY} {table}\n{result.stderr.strip()}"
        )


def partition_active(dev: str) -> bool:
    """Return True if the kvmchaos partition table exists for a tap device.

    Never raises — returns False on any nft failure so callers can use this
    for verify checks without try/except.

    Args:
        dev: Host tap device name.

    Returns:
        True if the table exists, False otherwise.
    """
    table = _table_name(dev)
    result = subprocess.run(
        ["nft", "list", "table", _TABLE_FAMILY, table],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run(cmd: list[str]) -> None:
    """Run an nft command, raising RuntimeError on non-zero exit.

    Args:
        cmd: Full command list including ``'nft'`` as first element.

    Raises:
        RuntimeError: If the command exits non-zero.
    """
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"nft command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
