"""`disk.latency` fault — throttle VM disk I/O via cgroup v2 io.max.

Writes a bandwidth limit to the QEMU process's blkio cgroup, causing all
disk I/O from the VM to be throttled to ``bandwidth_bps`` bytes per second.

Requires root (cgroup writes are privileged). The VM disk must be a file-backed
device (qcow2 or raw) on a local filesystem.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar

import libvirt


class DiskLatencyFault:
    """Throttle VM disk I/O to simulate slow storage via cgroup v2 io.max.

    Implements the ``Fault`` protocol. Unlike other faults, this class is
    stateful: ``bandwidth_bps`` is set at construction time and used across
    inject/verify/revert.
    """

    name: ClassVar[str] = "disk.latency"
    description: ClassVar[str] = "Throttle VM disk I/O to N MB/s via cgroup v2 io.max."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, bandwidth_bps: int = 1_000_000) -> None:
        """Initialise with a bandwidth limit.

        Args:
            bandwidth_bps: Throttle limit in bytes per second. Default 1 MB/s.
        """
        self.bandwidth_bps = bandwidth_bps

    def inject(self, domain: libvirt.virDomain) -> None:
        """Throttle the domain's disk I/O via cgroup io.max.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            FileNotFoundError: If the QEMU PID file is not found (VM not running).
            RuntimeError: If the cgroup path or disk device cannot be resolved.
            PermissionError: If writing to the cgroup requires elevated privileges.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        io_max.write_text(f"{major}:{minor} rbps={self.bandwidth_bps} wbps={self.bandwidth_bps}\n")

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the io.max throttle is in effect.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the throttle entry is absent or has wrong values.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        content = io_max.read_text()
        expected = f"{major}:{minor} rbps={self.bandwidth_bps} wbps={self.bandwidth_bps}"
        if expected not in content:
            raise RuntimeError(
                f"disk.latency not in effect for {domain.name()}: expected {expected!r} in io.max"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the io.max throttle, restoring full disk I/O speed.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the cgroup path cannot be resolved.
        """
        major, minor = _disk_dev(domain)
        io_max = _io_max_path(domain.name())
        io_max.write_text(f"{major}:{minor} rbps=max wbps=max\n")


def _qemu_pid(vm_name: str) -> int:
    """Read the QEMU PID from libvirt's pid file for the named domain.

    Args:
        vm_name: libvirt domain name.

    Returns:
        Integer PID of the running QEMU process.

    Raises:
        FileNotFoundError: If the PID file does not exist (VM not running).
    """
    return int(Path(f"/var/run/libvirt/qemu/{vm_name}.pid").read_text().strip())


def _io_max_path(vm_name: str) -> Path:
    """Resolve the absolute path to the cgroup io.max file for a QEMU process.

    Reads ``/proc/<pid>/cgroup`` to find the cgroups v2 path, then constructs
    the absolute path under ``/sys/fs/cgroup``.

    Args:
        vm_name: libvirt domain name.

    Returns:
        Absolute ``Path`` to the ``io.max`` file.

    Raises:
        FileNotFoundError: If the PID file does not exist.
        RuntimeError: If no cgroups v2 entry is found in the process cgroup file.
    """
    pid = _qemu_pid(vm_name)
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            rel = line[3:].lstrip("/")
            return Path("/sys/fs/cgroup") / rel / "io.max"
    raise RuntimeError(f"cgroups v2 hierarchy not found in /proc/{pid}/cgroup")


def _disk_dev(domain: libvirt.virDomain) -> tuple[int, int]:
    """Return (major, minor) of the filesystem device holding the VM's first disk.

    Parses the domain XML to find the first ``<disk device='disk'>`` source file,
    then calls ``os.stat`` to get the device numbers of the filesystem it lives on.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Tuple of (major, minor) integers for use in cgroup io.max entries.

    Raises:
        RuntimeError: If no disk source file is found in the domain XML.
    """
    root = ET.fromstring(domain.XMLDesc())
    elem = root.find(".//disk[@device='disk']/source")
    if elem is None:
        raise RuntimeError(f"No disk source found in domain XML for {domain.name()}")
    source_file = elem.get("file")
    if not source_file:
        raise RuntimeError(f"Disk source has no file attribute for {domain.name()}")
    st = os.stat(source_file)
    return os.major(st.st_dev), os.minor(st.st_dev)
