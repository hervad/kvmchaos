"""`net.packet-loss` fault — inject packet loss on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to drop a fixed percentage of
packets. The tap device name is resolved via :func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_LOSS_PERCENT: int = 10


class NetPacketLossFault:
    """Injects packet loss via tc netem on the host tap device.

    Implements the ``Fault`` protocol. Stateful: ``loss_percent`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.packet-loss"
    description: ClassVar[str] = (
        f"Drop {_DEFAULT_LOSS_PERCENT}% of packets on first vNIC via tc netem."
    )
    destructive: ClassVar[bool] = False

    def __init__(self, loss_percent: int = _DEFAULT_LOSS_PERCENT) -> None:
        """Initialise with a packet-loss percentage.

        Args:
            loss_percent: Percentage of packets to drop (0-100). Default 50.
        """
        self.loss_percent = loss_percent

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem packet loss to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_loss(tc.tap_device(domain), self.loss_percent)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem packet loss is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or loss is not configured.
        """
        tc.assert_netem_active(
            tc.tap_device(domain), domain.name(), keyword="loss", label="packet loss"
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
