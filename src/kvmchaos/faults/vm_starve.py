"""`vm.starve` fault — squeeze a running domain's memory via balloon driver.

Balloons the guest memory to 25% of its configured maximum, forcing the
guest OS to swap. Reverts by ballooning back to the configured maximum.

Requires the guest to have a virtio-balloon driver loaded (standard for
QEMU/KVM guests). Raises libvirtError if the driver is absent.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt


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
        """Assert balloon target is at or below 50% of configured maximum.

        Uses a 50% bound (rather than exactly 25%) to tolerate balloon
        driver settling latency.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If memory is still above 50% of max after inject.
            libvirt.libvirtError: On libvirt API failure.
        """
        stats = domain.memoryStats()
        actual = stats.get("actual", domain.maxMemory())
        threshold = domain.maxMemory() // 2
        if actual > threshold:
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
