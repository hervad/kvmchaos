"""`vm.pause` fault — suspend a running domain's vCPUs.

Freezes vCPU execution while keeping RAM contents intact. The guest does
not observe the pause directly, but its clock will drift relative to wall
time for the duration. Reverted by `virDomain.resume()`.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt


class VmPauseFault:
    """Pauses a running VM via `virDomain.suspend()`.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "vm.pause"
    description: ClassVar[str] = "Suspend vCPUs; RAM preserved. Guest clock drifts."
    destructive: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Suspend the domain's vCPUs.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the suspend call fails.
        """
        domain.suspend()

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert the domain is in the paused state.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the domain is not paused after inject.
            libvirt.libvirtError: On libvirt API failure.
        """
        state, _ = domain.state()
        if state != libvirt.VIR_DOMAIN_PAUSED:
            raise RuntimeError(f"domain '{domain.name()}' not paused after inject (state={state})")

    def revert(self, domain: libvirt.virDomain) -> None:
        """Resume the domain's vCPUs.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the resume call fails for a reason other
                than the domain already being in the running state.
        """
        try:
            domain.resume()
        except libvirt.libvirtError:
            # Idempotent: if the domain is already running (e.g. a sibling
            # thread's revert beat us to it), the desired end-state is met.
            if domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                return
            raise
