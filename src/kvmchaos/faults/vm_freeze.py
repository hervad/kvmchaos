"""`vm.freeze` fault — hard-cap a running domain's vCPU time via quota.

Sets vcpu_quota to 5000 µs per 100 000 µs period (5% of one vCPU), which
is a hard CFS bandwidth limit enforced by the kernel regardless of host load.
Reverts to -1 (unlimited).

Note: revert restores to unlimited (-1) regardless of any pre-inject quota.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

# 5 % of one vCPU per scheduler period — observable even on an idle host.
_QUOTA_THROTTLED: int = 5000
_QUOTA_UNLIMITED: int = -1


class VmFreezeFault:
    """Hard-caps a running VM's vCPU time to 5% via libvirt scheduler quota.

    Implements the `Fault` protocol — stateless, operates on a provided
    `virDomain` handle.
    """

    name: ClassVar[str] = "vm.freeze"
    description: ClassVar[str] = "Hard-cap vCPU quota to 5%; guest crawls regardless of host load."
    destructive: ClassVar[bool] = False
    local_only: ClassVar[bool] = False

    def inject(self, domain: libvirt.virDomain) -> None:
        """Set vcpu_quota to 5% of one vCPU period.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        domain.setSchedulerParameters({"vcpu_quota": _QUOTA_THROTTLED})

    def verify(self, domain: libvirt.virDomain) -> None:
        """Assert vcpu_quota is at the throttled value.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            RuntimeError: If vcpu_quota is not throttled after inject.
            libvirt.libvirtError: On libvirt API failure.
        """
        params = domain.schedulerParameters()
        if params.get("vcpu_quota") != _QUOTA_THROTTLED:
            raise RuntimeError(
                f"domain '{domain.name()}' not throttled after inject "
                f"(vcpu_quota={params.get('vcpu_quota')})"
            )

    def revert(self, domain: libvirt.virDomain) -> None:
        """Restore vcpu_quota to unlimited (-1).

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        domain.setSchedulerParameters({"vcpu_quota": _QUOTA_UNLIMITED})
