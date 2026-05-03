"""`vm.freeze` fault — hard-cap a running domain's vCPU time via quota.

Sets vcpu_quota to 5000 µs per 100 000 µs period (5% of one vCPU), which
is a hard CFS bandwidth limit enforced by the kernel regardless of host load.
Revert restores the quota that was in place before inject was called.
"""

from __future__ import annotations

from typing import ClassVar

import libvirt

# 5 % of one vCPU per scheduler period — observable even on an idle host.
_QUOTA_THROTTLED: int = 5000
_QUOTA_UNLIMITED: int = -1


class VmFreezeFault:
    """Hard-caps a running VM's vCPU time to 5% via libvirt scheduler quota.

    Implements the ``Fault`` protocol. Stateful: saves the pre-inject quota in
    ``inject`` and restores it in ``revert``.
    """

    name: ClassVar[str] = "vm.freeze"
    description: ClassVar[str] = "Hard-cap vCPU quota to 5%; guest crawls regardless of host load."
    destructive: ClassVar[bool] = False

    def __init__(self) -> None:
        """Initialise with no saved quotas."""
        self._original_quotas: dict[str, int] = {}

    def inject(self, domain: libvirt.virDomain) -> None:
        """Save the current vcpu_quota then set it to 5% of one vCPU period.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        params = domain.schedulerParameters()
        self._original_quotas[domain.name()] = int(params.get("vcpu_quota", _QUOTA_UNLIMITED))
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
        """Restore vcpu_quota to the value saved during inject.

        Args:
            domain: A live libvirt domain handle.

        Raises:
            libvirt.libvirtError: If the scheduler call fails.
        """
        quota = self._original_quotas.pop(domain.name(), _QUOTA_UNLIMITED)
        domain.setSchedulerParameters({"vcpu_quota": quota})
