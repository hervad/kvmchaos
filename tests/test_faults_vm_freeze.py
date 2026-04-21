"""Tests for vm.freeze."""

# test:///default does not implement cpu_shares scheduler attribute (QEMU-specific),
# so all tests use MagicMock(spec=libvirt.virDomain).

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_freeze import VmFreezeFault


class TestVmFreezeMetadata:
    def test_name(self):
        assert VmFreezeFault.name == "vm.freeze"

    def test_description_present(self):
        assert VmFreezeFault.description

    def test_non_destructive(self):
        assert VmFreezeFault.destructive is False


class TestVmFreezeHappyPath:
    def _mock_domain(self, cpu_shares: int = 2) -> MagicMock:
        domain = MagicMock(spec=libvirt.virDomain)
        domain.name.return_value = "testvm"
        domain.schedulerParameters.return_value = {"cpu_shares": cpu_shares}
        return domain

    def test_inject_sets_minimum_cpu_shares(self):
        domain = self._mock_domain()
        VmFreezeFault().inject(domain)
        domain.setSchedulerParameters.assert_called_once_with({"cpu_shares": 2})

    def test_verify_passes_when_shares_are_minimum(self):
        domain = self._mock_domain(cpu_shares=2)
        VmFreezeFault().verify(domain)  # must not raise

    def test_verify_raises_when_shares_not_minimum(self):
        domain = self._mock_domain(cpu_shares=1024)
        with pytest.raises(RuntimeError, match="not throttled"):
            VmFreezeFault().verify(domain)

    def test_revert_restores_default_shares(self):
        domain = self._mock_domain()
        VmFreezeFault().revert(domain)
        domain.setSchedulerParameters.assert_called_once_with({"cpu_shares": 1024})


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
