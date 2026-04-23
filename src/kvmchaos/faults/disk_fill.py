"""`disk.fill` fault — exhaust host-side disk space near the VM image.

Creates a preallocated fill file in the same directory as the VM's qcow2
image, consuming ``fill_bytes`` of host filesystem space. The guest sees
ENOSPC on subsequent disk writes once the host volume is full.

Requires write permission to the image directory (typically root or the
``libvirt-qemu`` user). Reverts by deleting the fill file.
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar

import libvirt

_FILL_PREFIX = ".kvmchaos-fill-"


class DiskFillFault:
    """Fill host disk space near the VM image to trigger guest ENOSPC.

    Implements the ``Fault`` protocol. Stateful: ``fill_bytes`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "disk.fill"
    description: ClassVar[str] = "Fill host disk near VM image to trigger guest ENOSPC."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, fill_bytes: int = 1_073_741_824) -> None:
        """Initialise with a fill size.

        Args:
            fill_bytes: Bytes to allocate on the host filesystem. Default 1 GiB.
        """
        self.fill_bytes = fill_bytes

    def inject(self, domain: libvirt.virDomain) -> None:
        """Create a preallocated fill file next to the VM's disk image.

        Uses ``fallocate -l`` for instant allocation; falls back to ``dd`` if
        fallocate is unavailable.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the fill file cannot be created.
            PermissionError: If write access to the image directory is denied.
        """
        image = _image_path(domain)
        free = shutil.disk_usage(image.parent).free
        if self.fill_bytes > int(free * 0.8):
            raise RuntimeError(
                f"insufficient disk space for disk.fill on '{domain.name()}': "
                f"requested {self.fill_bytes} bytes but only {free} bytes free "
                f"(limit is 80% of free space)"
            )
        fill = _fill_path(image, domain.name())
        try:
            subprocess.run(
                ["fallocate", "-l", str(self.fill_bytes), str(fill)],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError:
            # fallocate not available — fall back to dd with sparse file
            try:
                subprocess.run(
                    [
                        "dd",
                        "if=/dev/zero",
                        f"of={fill}",
                        "bs=1M",
                        f"count={max(1, self.fill_bytes // (1024 * 1024))}",
                    ],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"disk.fill inject failed for {domain.name()}: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"disk.fill inject failed for {domain.name()}: {exc}") from exc

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the fill file exists on the host filesystem.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the fill file is absent.
        """
        image = _image_path(domain)
        fill = _fill_path(image, domain.name())
        if not fill.exists():
            raise RuntimeError(
                f"disk.fill not in effect for {domain.name()}: fill file not found at {fill}"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Delete the fill file, restoring host disk space.

        Idempotent: does nothing if the fill file is already absent.

        Args:
            domain: A live libvirt domain handle.
        """
        image = _image_path(domain)
        fill = _fill_path(image, domain.name())
        fill.unlink(missing_ok=True)


def _image_path(domain: libvirt.virDomain) -> Path:
    """Extract the first disk image path from the domain XML.

    Args:
        domain: A live libvirt domain handle.

    Returns:
        Absolute ``Path`` to the qcow2/raw image file.

    Raises:
        RuntimeError: If no ``<disk device='disk'>`` source is found, or the
            source has no ``file`` attribute.
    """
    root = ET.fromstring(domain.XMLDesc())
    elem = root.find(".//disk[@device='disk']/source")
    if elem is None:
        raise RuntimeError(f"No disk source found in domain XML for {domain.name()}")
    source_file = elem.get("file")
    if not source_file:
        raise RuntimeError(f"Disk source has no file attribute for {domain.name()}")
    return Path(source_file)


def _fill_path(image: Path, vm_name: str) -> Path:
    """Return the path of the fill file for the given VM.

    The fill file is placed in the same directory as the disk image so that
    it consumes space on the same filesystem.

    Args:
        image: Path to the VM's disk image file.
        vm_name: libvirt domain name.

    Returns:
        ``Path`` for the fill file (hidden file, prefixed with ``_FILL_PREFIX``).
    """
    return image.parent / f"{_FILL_PREFIX}{vm_name}"
