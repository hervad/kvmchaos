"""`clock.skew` fault — shift a VM's guest clock by a fixed offset.

Uses the libvirt ``setTime``/``getTime`` API (backed by QEMU guest agent) to
move the guest clock forward or backward by ``skew_seconds``. Reverts by
resetting to the host wall clock.

Requires ``qemu-guest-agent`` to be running inside the guest.
"""

from __future__ import annotations

import time
from typing import ClassVar

import libvirt

_DEFAULT_SKEW: int = 3600  # 1 hour forward
_VERIFY_TOLERANCE: int = 30  # seconds; accounts for agent round-trip latency


class ClockSkewFault:
    """Shift the guest clock by a fixed offset via libvirt setTime/getTime.

    Implements the ``Fault`` protocol. Stateful: stores the expected skewed
    time after inject so verify and revert can act on it.

    Requires ``qemu-guest-agent`` running in the guest.
    """

    name: ClassVar[str] = "clock.skew"
    description: ClassVar[str] = (
        f"Shift guest clock by {_DEFAULT_SKEW}s via QEMU guest agent setTime."
    )
    destructive: ClassVar[bool] = False

    def __init__(self, skew_seconds: int = _DEFAULT_SKEW) -> None:
        """Initialise with a clock offset.

        Args:
            skew_seconds: Seconds to add to the guest clock. Negative values
                shift the clock backward. Default 3600 (1 hour forward).
        """
        self.skew_seconds = skew_seconds
        self._expected: dict[str, int] = {}

    def inject(self, domain: libvirt.virDomain) -> None:
        """Shift the guest clock by ``skew_seconds``.

        Reads the current guest time, adds the skew, and writes it back.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the guest agent is unavailable or the
                setTime call fails.
        """
        current = domain.getTime()
        target = current["seconds"] + self.skew_seconds
        domain.setTime({"seconds": target, "nseconds": 0})
        self._expected[domain.name()] = target

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that the guest clock is within tolerance of the skewed value.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If inject has not been called, or if the guest clock
                is not within ``_VERIFY_TOLERANCE`` seconds of the expected value.
            libvirt.libvirtError: If the guest agent call fails.
        """
        expected = self._expected.get(domain.name())
        if expected is None:
            raise RuntimeError(f"clock.skew not injected on '{domain.name()}' — call inject first")
        actual = domain.getTime()["seconds"]
        delta = abs(actual - expected)
        if delta > _VERIFY_TOLERANCE:
            raise RuntimeError(
                f"clock skew not in effect on '{domain.name()}': "
                f"expected ~{expected}, got {actual} (delta {delta}s)"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Reset the guest clock to the current host wall clock time.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If inject has not been called.
            libvirt.libvirtError: If the guest agent call fails.
        """
        if self._expected.pop(domain.name(), None) is None:
            raise RuntimeError(f"clock.skew not injected on '{domain.name()}' — call inject first")
        now = int(time.time())
        domain.setTime({"seconds": now, "nseconds": 0})
