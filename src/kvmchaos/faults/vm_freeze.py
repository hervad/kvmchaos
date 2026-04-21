"""`vm.freeze` fault — throttle a running domain's CPU scheduler shares.

Sets cpu_shares to the minimum (2), causing the guest to receive near-zero
CPU time while remaining alive. Reverts to the QEMU/KVM default of 1024.

Note: revert restores to 1024 regardless of the pre-inject value. If the
domain had a custom cpu_shares, that value is not preserved.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt


class VmFreezeFault:
    """Throttles a running VM's CPU shares to minimum via libvirt scheduler API.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "vm.freeze"
    description: ClassVar[str] = "Throttle CPU shares to minimum; guest runs near-zero speed."
    destructive: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Set CPU shares to minimum (2).

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        domain.setSchedulerParameters({"cpu_shares": 2})

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert CPU shares are at minimum.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If cpu_shares are not 2 after inject.
            libvirt.libvirtError: On libvirt API failure.
        """
        params = domain.schedulerParameters()
        if params.get("cpu_shares") != 2:
            raise RuntimeError(
                f"domain '{domain.name()}' not throttled after inject "
                f"(cpu_shares={params.get('cpu_shares')})"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Restore CPU shares to QEMU/KVM default (1024).

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        domain.setSchedulerParameters({"cpu_shares": 1024})
