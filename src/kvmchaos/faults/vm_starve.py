"""`vm.starve` fault — squeeze a running domain's memory via balloon driver.

Balloons the guest memory to 25% of its configured maximum, forcing the
guest OS to swap. Reverts by ballooning back to the configured maximum.

Requires the guest to have a virtio-balloon driver loaded (standard for
QEMU/KVM guests). Raises libvirtError if the driver is absent.
"""

from __future__ import annotations

import time
from typing import ClassVar

import libvirt

_VERIFY_RETRIES = 5
_VERIFY_SLEEP = 1.0  # seconds between retries


class VmStarveFault:
    """Squeezes a running VM's memory to 25% of max via the balloon driver.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle. `maxMemory()` is read fresh at each step so no
    instance state is needed.
    """

    name: ClassVar[str] = "vm.starve"
    description: ClassVar[str] = "Balloon memory to 25% of max; guest swaps heavily."
    destructive: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Balloon domain memory to 25% of its configured maximum.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the balloon call fails (e.g. no driver).
        """
        domain.setMemory(domain.maxMemory() // 4)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert balloon has settled at or below 50% of configured maximum.

        Retries up to _VERIFY_RETRIES times with a short sleep to allow the
        guest balloon driver time to respond to the setMemory call.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If memory remains above 50% of max after all retries.
            libvirt.libvirtError: On libvirt API failure.
        """
        threshold = domain.maxMemory() // 2
        for attempt in range(_VERIFY_RETRIES):
            actual = domain.memoryStats().get("actual", domain.maxMemory())
            if actual <= threshold:
                return
            if attempt < _VERIFY_RETRIES - 1:
                time.sleep(_VERIFY_SLEEP)
        raise RuntimeError(
            f"domain '{domain.name()}' not starved after inject "
            f"(actual={actual}KB, threshold={threshold}KB)"
        )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Balloon domain memory back to its configured maximum.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the balloon call fails.
        """
        domain.setMemory(domain.maxMemory())
