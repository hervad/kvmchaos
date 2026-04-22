"""`vm.kill` fault — forcefully terminate a running domain.

Uses a graceful-first destroy: SIGTERM is sent first, escalating to SIGKILL
on timeout. Any unsaved guest state is lost. Reverted by restarting the
domain from its persisted definition, which requires the domain to be
persistently defined (the normal case for `qemu:///system`).
"""

from __future__ import annotations

from typing import ClassVar

import libvirt


class VmKillFault:
    """Destroys a running VM then restarts it from its defined config.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "vm.kill"
    description: ClassVar[str] = "Graceful destroy then restart. Unsaved state lost."
    destructive: ClassVar[bool] = True
    local_only: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Destroy the domain using graceful-first termination.

        Sends SIGTERM to the guest, escalating to SIGKILL on timeout.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the destroy call fails.
        """
        domain.destroyFlags(libvirt.VIR_DOMAIN_DESTROY_GRACEFUL)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert the domain is in the shut-off state.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the domain is not shut off after inject.
            libvirt.libvirtError: On libvirt API failure.
        """
        state, _ = domain.state()
        if state != libvirt.VIR_DOMAIN_SHUTOFF:
            raise RuntimeError(
                f"domain '{domain.name()}' not shut off after inject (state={state})"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Start the domain from its persisted definition.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the start call fails.
        """
        domain.create()
