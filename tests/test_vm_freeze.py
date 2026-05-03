"""Tests for vm.freeze fault."""

from __future__ import annotations

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_freeze import _QUOTA_THROTTLED, _QUOTA_UNLIMITED, VmFreezeFault


def _mock_domain(name: str = "server1", quota: int = _QUOTA_UNLIMITED) -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = name
    domain.schedulerParameters.return_value = {"vcpu_quota": quota}
    return domain


class TestVmFreezeMetadata:
    def test_name(self):
        assert VmFreezeFault.name == "vm.freeze"

    def test_description_present(self):
        assert VmFreezeFault.description

    def test_non_destructive(self):
        assert VmFreezeFault.destructive is False


class TestVmFreezeInject:
    def test_inject_sets_throttled_quota(self):
        domain = _mock_domain()
        VmFreezeFault().inject(domain)
        domain.setSchedulerParameters.assert_called_once_with({"vcpu_quota": _QUOTA_THROTTLED})

    def test_inject_reads_current_quota_before_throttling(self):
        domain = _mock_domain(quota=8000)
        fault = VmFreezeFault()
        fault.inject(domain)
        assert domain.schedulerParameters.call_count == 1


class TestVmFreezeVerify:
    def test_verify_passes_when_throttled(self):
        domain = _mock_domain()
        domain.schedulerParameters.return_value = {"vcpu_quota": _QUOTA_THROTTLED}
        VmFreezeFault().verify(domain)  # must not raise

    def test_verify_raises_when_not_throttled(self):
        domain = _mock_domain()
        domain.schedulerParameters.return_value = {"vcpu_quota": _QUOTA_UNLIMITED}
        with pytest.raises(RuntimeError, match="not throttled"):
            VmFreezeFault().verify(domain)


class TestVmFreezeRevert:
    def test_revert_restores_original_quota(self):
        domain = _mock_domain(quota=8000)
        fault = VmFreezeFault()
        fault.inject(domain)
        fault.revert(domain)
        domain.setSchedulerParameters.assert_called_with({"vcpu_quota": 8000})

    def test_revert_without_inject_uses_unlimited(self):
        """Revert without prior inject must not raise; restores unlimited (safe default)."""
        domain = _mock_domain()
        fault = VmFreezeFault()
        fault.revert(domain)  # must not raise
        domain.setSchedulerParameters.assert_called_once_with({"vcpu_quota": _QUOTA_UNLIMITED})

    def test_parallel_domains_keep_independent_quotas(self):
        """Singleton fault must not mix up pre-inject quotas across parallel VM workers."""
        domain_a = _mock_domain(name="vm-a", quota=5000)
        domain_b = _mock_domain(name="vm-b", quota=_QUOTA_UNLIMITED)

        fault = VmFreezeFault()
        fault.inject(domain_a)  # saves 5000 for vm-a
        fault.inject(domain_b)  # saves -1 for vm-b; must NOT overwrite vm-a's value

        fault.revert(domain_a)

        # vm-a's original quota (5000) must be restored, not vm-b's (-1)
        domain_a.setSchedulerParameters.assert_called_with({"vcpu_quota": 5000})
