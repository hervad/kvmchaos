"""`net.latency` fault — inject one-way latency on a VM's first virtual NIC.

Uses ``tc netem`` on the host-side tap device to add a fixed one-way delay.
The tap device name is resolved via :func:`kvmchaos.tc.tap_device`.

Requires root or CAP_NET_ADMIN on the host. All other faults are unaffected
by this privilege requirement.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

import kvmchaos.tc as tc

_DELAY_MS: int = 200


class NetLatencyFault:
    """Injects one-way network latency via tc netem on the host tap device.

    Implements the ``Fault`` protocol — stateless, operates on a provided
    ``virDomain`` handle.
    """

    name: ClassVar[str] = "net.latency"
    description: ClassVar[str] = f"Add {_DELAY_MS}ms one-way latency to first vNIC via tc netem."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = True

    def inject(self, domain: libvirt.virDomain) -> None:
        """Apply netem delay to the domain's first tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails (e.g. permission denied).
        """
        tc.add_netem_delay(tc.tap_device(domain), _DELAY_MS)

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert that a netem qdisc is active on the tap device.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If netem is not present in tc qdisc show output.
        """
        tc.assert_netem_active(tc.tap_device(domain), domain.name())

    def revert(self, domain: libvirt.virDomain) -> None:
        """Remove the root qdisc from the tap device, restoring kernel default.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If no network interface is found in the domain XML.
            RuntimeError: If the tc command fails.
        """
        tc.del_root_qdisc(tc.tap_device(domain))
