"""`net.corrupt` fault — inject packet corruption on a VM's first virtual NIC.

Uses ``tc netem corrupt N%`` on the host-side tap device to corrupt a fixed
percentage of packets. The tap device name is resolved via
:func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_CORRUPT_PERCENT: int = 1


class NetCorruptFault:
    """Injects random bit corruption into a VM's first vNIC packets via tc netem.

    Implements the ``Fault`` protocol. Stateful: ``corrupt_percent`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.corrupt"
    description: ClassVar[str] = (
        f"Corrupt {_DEFAULT_CORRUPT_PERCENT}% of packets on first vNIC via tc netem corrupt."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, corrupt_percent: int = _DEFAULT_CORRUPT_PERCENT) -> None:
        """Initialise with a corruption percentage.

        Args:
            corrupt_percent: Percentage of packets to corrupt (1-100). Default 1.
        """
        self.corrupt_percent = corrupt_percent

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem corrupt rule to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_corrupt(tc.tap_device(domain), self.corrupt_percent)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem packet corruption is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or corrupt is not configured.
        """
        tc.assert_netem_active(
            tc.tap_device(domain), domain.name(), keyword="corrupt", label="corruption"
        )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(tc.tap_device(domain))
