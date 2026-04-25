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

        If the QEMU process has exited since inject (e.g. the VM was force-stopped),
        the cgroup is already gone and the throttle no longer applies. In that case
        this method returns without error rather than raising.

        Args:
            domain: A live libvirt domain handle.
        """
        try:
            major, minor = _disk_dev(domain)
            io_max = _io_max_path(domain.name())
        except (FileNotFoundError, RuntimeError):
            # QEMU exited; cgroup is already cleaned up — throttle is gone.
            return
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

    The PID's immediate cgroup (e.g. ``.../libvirt/emulator``) often does not
    have the ``io`` controller delegated — libvirt enables ``io`` only at the
    ``.../libvirt`` or ``.../scope`` level. This function walks up from the
    PID's cgroup to the nearest ancestor whose ``cgroup.controllers`` contains
    ``io``. Throttles set on a parent cgroup apply to all descendant processes.

    Args:
        vm_name: libvirt domain name.

    Returns:
        Absolute ``Path`` to the ``io.max`` file.

    Raises:
        FileNotFoundError: If the PID file does not exist.
        RuntimeError: If no cgroups v2 entry is found, or no ancestor has the
            io controller enabled.
    """
    pid = _qemu_pid(vm_name)
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            rel = line[3:].lstrip("/")  # Path("/x") / "/abs" silently drops "/x" in Python
            return _find_io_cgroup(Path("/sys/fs/cgroup") / rel) / "io.max"
    raise RuntimeError(f"cgroups v2 hierarchy not found in /proc/{pid}/cgroup")


def _find_io_cgroup(start: Path) -> Path:
    """Walk up from ``start`` to the nearest cgroup with the io controller.

    Args:
        start: A cgroup v2 directory (or deeper leaf).

    Returns:
        Absolute ``Path`` of the nearest ancestor (including ``start`` itself)
        whose ``cgroup.controllers`` file lists ``io``.

    Raises:
        RuntimeError: If no ancestor with io in its controllers is found
            before leaving the cgroup hierarchy.
    """
    current = start
    while True:
        controllers = current / "cgroup.controllers"
        if not controllers.is_file():
            break
        if "io" in controllers.read_text().split():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(f"no ancestor of {start} has io controller enabled")


def _disk_dev(domain: libvirt.virDomain) -> tuple[int, int]:
    """Return (major, minor) of the whole block device backing the VM's disk.

    Parses the domain XML to find the first ``<disk device='disk'>`` source
    file, uses ``/proc/self/mountinfo`` to map that path to its backing block
    device (handling btrfs/xfs/ext4 on partitions, LVM, etc.), stats the block
    device to get its major:minor, then walks up to the whole disk.

    Going through ``mountinfo`` is required because ``os.stat(file).st_dev``
    returns an anonymous device number for filesystems that synthesize one
    (notably btrfs subvolumes, which report major 0), and those anonymous
    numbers are rejected by cgroup v2 ``io.max`` with ``ENODEV``.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Tuple of (major, minor) integers for use in cgroup io.max entries.

    Raises:
        RuntimeError: If no disk source is found, or the backing device
            cannot be resolved to a real block device.

    Note:
        Assumes the image file resides on a single block device. LVM volumes,
        bcache, and btrfs RAID configurations are not supported.
    """
    root = ET.fromstring(domain.XMLDesc())
    elem = root.find(".//disk[@device='disk']/source")
    if elem is None:
        raise RuntimeError(f"No disk source found in domain XML for {domain.name()}")
    source_file = elem.get("file")
    if not source_file:
        raise RuntimeError(f"Disk source has no file attribute for {domain.name()}")
    blk = _backing_block_device(Path(source_file))
    st = os.stat(blk)
    return _whole_disk(os.major(st.st_rdev), os.minor(st.st_rdev))


def _backing_block_device(path: Path) -> Path:
    """Return the ``/dev/...`` block device that backs the filesystem of ``path``.

    Parses ``/proc/self/mountinfo`` and picks the entry whose mount point is
    the longest prefix of ``path``. Works for plain partitions, LVM, dm-crypt,
    and btrfs (where ``os.stat`` reports an anonymous ``st_dev``).

    Args:
        path: Absolute path to a file or directory on a mounted filesystem.

    Returns:
        ``Path`` to the block device (e.g. ``/dev/nvme0n1p6``).

    Raises:
        RuntimeError: If no mount entry covers ``path``, or the resolved
            source is not a ``/dev/...`` block device (e.g. tmpfs, overlay).
    """
    target = str(path.resolve())
    best_mount = ""
    best_source = ""
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        # mountinfo fields: id parent major:minor root mnt_point opts ... - fs source fs_opts
        left, sep, right = line.partition(" - ")
        if not sep:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or len(right_fields) < 2:
            continue
        mount_point = left_fields[4]
        source = right_fields[1]
        covered = target == mount_point or target.startswith(mount_point.rstrip("/") + "/")
        if covered and len(mount_point) > len(best_mount):
            best_mount = mount_point
            best_source = source
    if not best_source.startswith("/dev/"):
        raise RuntimeError(
            f"cannot resolve {path} to a block device (mountinfo source: {best_source!r})"
        )
    return Path(best_source)


def _whole_disk(major: int, minor: int) -> tuple[int, int]:
    """Resolve a (possibly partition) device to its whole-disk (major, minor).

    cgroup v2 ``io.max`` is enforced at the request_queue level, which exists
    only on whole disks. Writing a partition's major:minor is silently ignored
    on most kernels, so partitions must be walked up to their parent disk.

    Args:
        major: Device major number (may be a partition).
        minor: Device minor number.

    Returns:
        Tuple of (major, minor) for the whole disk. If the input is already
        a whole disk, returns it unchanged. If ``/sys`` entries are missing
        (non-Linux or unusual block device), returns the input unchanged.
    """
    sys_link = Path(f"/sys/dev/block/{major}:{minor}")
    try:
        real = Path(os.path.realpath(sys_link))
    except OSError:
        return major, minor
    parent_dev = real.parent / "dev"
    if not parent_dev.is_file():
        return major, minor
    try:
        text = parent_dev.read_text().strip()
        pmaj_s, pmin_s = text.split(":", 1)
        return int(pmaj_s), int(pmin_s)
    except (OSError, ValueError):
        return major, minor
