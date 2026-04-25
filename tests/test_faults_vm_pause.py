"""Tests for vm.pause."""

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_pause import VmPauseFault


class TestVmPauseHappyPath:
    def test_inject_pauses_domain(self, running_domain):
        VmPauseFault().inject(running_domain)
        state, _ = running_domain.state()
        assert state == libvirt.VIR_DOMAIN_PAUSED

    def test_verify_passes_when_paused(self, running_domain):
        fault = VmPauseFault()
        fault.inject(running_domain)
        fault.verify(running_domain)  # must not raise

    def test_verify_raises_when_not_paused(self, running_domain):
        with pytest.raises(RuntimeError, match="not paused"):
            VmPauseFault().verify(running_domain)

    def test_revert_resumes_domain(self, running_domain):
        fault = VmPauseFault()
        fault.inject(running_domain)
        fault.revert(running_domain)
        state, _ = running_domain.state()
        assert state == libvirt.VIR_DOMAIN_RUNNING


class TestVmPauseMetadata:
    def test_name(self):
        assert VmPauseFault.name == "vm.pause"

    def test_description_present(self):
        assert VmPauseFault.description

    def test_non_destructive(self):
        assert VmPauseFault.destructive is False


class TestVmPauseErrors:
    def test_inject_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.suspend.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmPauseFault().inject(domain)

    def test_revert_idempotent_when_already_running(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.resume.side_effect = libvirt.libvirtError("already running")
        domain.state.return_value = (libvirt.VIR_DOMAIN_RUNNING, 0)
        VmPauseFault().revert(domain)  # must not raise

    def test_revert_propagates_unexpected_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.resume.side_effect = libvirt.libvirtError("unexpected")
        domain.state.return_value = (libvirt.VIR_DOMAIN_PAUSED, 0)
        with pytest.raises(libvirt.libvirtError):
            VmPauseFault().revert(domain)
