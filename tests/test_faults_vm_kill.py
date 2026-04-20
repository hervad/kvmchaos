"""Tests for vm.kill."""

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_kill import VmKillFault


class TestVmKillHappyPath:
    def test_inject_shuts_off_domain(self, running_domain):
        VmKillFault().inject(running_domain)
        state, _ = running_domain.state()
        assert state == libvirt.VIR_DOMAIN_SHUTOFF

    def test_verify_passes_when_shutoff(self, running_domain):
        fault = VmKillFault()
        fault.inject(running_domain)
        fault.verify(running_domain)  # must not raise

    def test_verify_raises_when_still_running(self, running_domain):
        with pytest.raises(RuntimeError, match="not shut off"):
            VmKillFault().verify(running_domain)

    def test_revert_restarts_domain(self, running_domain):
        fault = VmKillFault()
        fault.inject(running_domain)
        fault.revert(running_domain)
        state, _ = running_domain.state()
        assert state == libvirt.VIR_DOMAIN_RUNNING


class TestVmKillMetadata:
    def test_name(self):
        assert VmKillFault.name == "vm.kill"

    def test_destructive(self):
        assert VmKillFault.destructive is True


class TestVmKillErrors:
    def test_inject_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.destroyFlags.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmKillFault().inject(domain)


class TestRegistry:
    def test_registry_contains_both_faults(self):
        from kvmchaos.faults import FAULTS

        assert "vm.pause" in FAULTS
        assert "vm.kill" in FAULTS
