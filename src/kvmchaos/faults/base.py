"""Structural type definition for chaos faults.

A fault is a stateless triple of operations against a libvirt domain:
inject → verify → revert.

`verify` confirms the fault actually took effect (not merely that the
libvirt call returned without error). `revert` returns the domain to its
pre-inject state.
"""

from __future__ import annotations

from typing import ClassVar, Protocol

import libvirt


class Fault(Protocol):
    """Structural interface that all fault implementations must satisfy.

    Fault classes are stateless — all state lives on the `virDomain`.
    The registry holds one singleton instance per fault class.
    """

    name: ClassVar[str]
    """Dotted identifier used as the registry key, e.g. ``'vm.pause'``."""

    description: ClassVar[str]
    """One-line human summary shown by ``kvmchaos list-faults``."""

    destructive: ClassVar[bool]
    """True if the fault kills or otherwise disrupts running guest state."""

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply the fault to the domain.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: On libvirt API failure.
        """
        ...

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the fault is in effect.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If the domain is not in the expected fault state.
            libvirt.libvirtError: On libvirt API failure.
        """
        ...

    def revert(self, domain: libvirt.virDomain) -> None:
        """Undo the fault and restore the domain to its pre-inject state.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: On libvirt API failure.
        """
        ...
