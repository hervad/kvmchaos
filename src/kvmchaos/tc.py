"""Thin subprocess wrapper for tc (iproute2) qdisc commands.

All functions that mutate qdisc state require root or CAP_NET_ADMIN on
the host. A non-zero exit from tc raises RuntimeError with the stderr output.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET

import libvirt


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


def add_netem_loss(dev: str, loss_percent: int) -> None:
    """Add or replace a netem qdisc with a fixed packet-loss rate on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        loss_percent: Percentage of packets to drop (0-100).

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "loss", f"{loss_percent}%"])


def add_netem_rate(dev: str, rate_kbps: int) -> None:
    """Add or replace a netem qdisc with a fixed rate limit on a network device.

    Uses ``replace`` so the call is idempotent if a qdisc already exists.

    Args:
        dev: Host network device name (e.g. ``'vnet0'``).
        rate_kbps: Bandwidth cap in kilobits per second.

    Raises:
        RuntimeError: If tc exits non-zero (e.g. device not found, no permission).
    """
    _run(["tc", "qdisc", "replace", "dev", dev, "root", "netem", "rate", f"{rate_kbps}kbit"])


def tap_device(domain: libvirt.virDomain) -> str:
    """Extract the first tap device name from the domain XML.

    Parses the ``<target dev="..."/>`` attribute of the first ``<interface>``
    element in the domain XML descriptor.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Host-side tap device name (e.g. ``'vnet0'``).

    Raises:
        RuntimeError: If no ``<interface>`` with a ``<target dev>`` is found.
    """
    root = ET.fromstring(domain.XMLDesc())
    target = root.find(".//interface/target[@dev]")
    if target is None:
        raise RuntimeError(f"no network interface found for domain '{domain.name()}'")
    return target.attrib["dev"]


def del_root_qdisc(dev: str) -> None:
    """Remove the root qdisc from a network device, restoring the kernel default.

    Idempotent: if no root qdisc is present (e.g. inject failed halfway through
    or revert is called twice), the function returns without raising.

    Args:
        dev: Host network device name.

    Raises:
        RuntimeError: If tc exits non-zero for a reason other than a missing qdisc.
    """
    result = subprocess.run(
        ["tc", "qdisc", "del", "dev", dev, "root"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "No such file or directory" not in result.stderr:
        raise RuntimeError(
            f"tc command failed: tc qdisc del dev {dev} root\n{result.stderr.strip()}"
        )


def show_qdisc(dev: str) -> str:
    """Return the output of ``tc qdisc show dev <dev>``.

    Never raises — returns empty string on failure so callers can
    inspect without catching exceptions.

    Note: An empty string is ambiguous — it may indicate that the
    device was not found, or that no qdisc is installed. Callers must
    be aware of this limitation and verify device existence separately
    if disambiguation is needed.

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
