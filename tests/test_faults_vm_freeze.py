"""Tests for vm.freeze."""

# test:///default does not implement vcpu_quota scheduler attribute (QEMU-specific),
# so all tests use MagicMock(spec=libvirt.virDomain).

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_freeze import _QUOTA_THROTTLED, _QUOTA_UNLIMITED, VmFreezeFault


class TestVmFreezeMetadata:
    def test_name(self):
        assert VmFreezeFault.name == "vm.freeze"

    def test_description_present(self):
        assert VmFreezeFault.description

    def test_non_destructive(self):
        assert VmFreezeFault.destructive is False


class TestVmFreezeHappyPath:
    def _mock_domain(self, vcpu_quota: int = _QUOTA_THROTTLED) -> MagicMock:
        domain = MagicMock(spec=libvirt.virDomain)
        domain.name.return_value = "testvm"
        domain.schedulerParameters.return_value = {"vcpu_quota": vcpu_quota}
        return domain

    def test_inject_sets_throttled_quota(self):
        domain = self._mock_domain()
        VmFreezeFault().inject(domain)
        domain.setSchedulerParameters.assert_called_once_with({"vcpu_quota": _QUOTA_THROTTLED})

    def test_verify_passes_when_quota_is_throttled(self):
        domain = self._mock_domain(vcpu_quota=_QUOTA_THROTTLED)
        VmFreezeFault().verify(domain)  # must not raise

    def test_verify_raises_when_quota_not_throttled(self):
        domain = self._mock_domain(vcpu_quota=_QUOTA_UNLIMITED)
        with pytest.raises(RuntimeError, match="not throttled"):
            VmFreezeFault().verify(domain)

    def test_revert_restores_unlimited_quota(self):
        domain = self._mock_domain()
        VmFreezeFault().revert(domain)
        domain.setSchedulerParameters.assert_called_once_with({"vcpu_quota": _QUOTA_UNLIMITED})


class TestVmFreezeErrors:
    def test_inject_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.setSchedulerParameters.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmFreezeFault().inject(domain)

    def test_verify_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.schedulerParameters.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmFreezeFault().verify(domain)

    def test_revert_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.setSchedulerParameters.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmFreezeFault().revert(domain)
