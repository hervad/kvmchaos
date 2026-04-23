"""`net.bandwidth` fault — cap a VM's first vNIC throughput via tc netem rate.

Uses ``tc netem rate`` on the host-side tap device to limit bandwidth to a
fixed number of kilobits per second. The tap device name is resolved via
:func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DEFAULT_RATE_KBPS: int = 1000


class NetBandwidthFault:
    """Caps a VM's first vNIC throughput via tc netem rate on the host tap device.

    Implements the ``Fault`` protocol. Stateful: ``rate_kbps`` is set at
    construction and used across inject/verify/revert.
    """

    name: ClassVar[str] = "net.bandwidth"
    description: ClassVar[str] = (
        f"Cap first vNIC throughput to {_DEFAULT_RATE_KBPS}kbps via tc netem rate."
    )
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def __init__(self, rate_kbps: int = _DEFAULT_RATE_KBPS) -> None:
        """Initialise with a bandwidth cap.

        Args:
            rate_kbps: Throughput limit in kilobits per second. Default 1000.
        """
        self.rate_kbps = rate_kbps

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem rate limit to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_rate(tc.tap_device(domain), self.rate_kbps)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that netem rate limiting is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present or rate is not configured.
        """
        tc.assert_netem_active(
            tc.tap_device(domain), domain.name(), keyword="rate", label="bandwidth limit"
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
