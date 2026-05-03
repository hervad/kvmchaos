"""Tests for vm.kill fault."""

from __future__ import annotations

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_kill import VmKillFault


def _mock_domain(name: str = "server1") -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = name
    return domain


class TestVmKillMetadata:
    def test_name(self):
        assert VmKillFault.name == "vm.kill"

    def test_description_present(self):
        assert VmKillFault.description

    def test_destructive(self):
        assert VmKillFault.destructive is True


class TestVmKillInject:
    def test_inject_calls_destroy_graceful(self):
        domain = _mock_domain()
        VmKillFault().inject(domain)
        domain.destroyFlags.assert_called_once_with(libvirt.VIR_DOMAIN_DESTROY_GRACEFUL)


class TestVmKillVerify:
    def test_verify_passes_when_shutoff(self):
        domain = _mock_domain()
        domain.state.return_value = (libvirt.VIR_DOMAIN_SHUTOFF, 0)
        VmKillFault().verify(domain)  # must not raise

    def test_verify_raises_when_still_running(self):
        domain = _mock_domain()
        domain.state.return_value = (libvirt.VIR_DOMAIN_RUNNING, 0)
        with pytest.raises(RuntimeError, match="not shut off"):
            VmKillFault().verify(domain)


class TestVmKillRevert:
    def test_revert_calls_create(self):
        domain = _mock_domain()
        VmKillFault().revert(domain)
        domain.create.assert_called_once()

    def test_revert_is_idempotent_when_domain_already_running(self):
        """If the domain restarted externally, revert must not raise."""
        domain = _mock_domain()
        domain.create.side_effect = libvirt.libvirtError("domain is already active")
        domain.state.return_value = (libvirt.VIR_DOMAIN_RUNNING, 0)
        VmKillFault().revert(domain)  # must not raise

    def test_revert_propagates_error_for_non_running_state(self):
        """libvirtError on create when domain is NOT running must propagate."""
        domain = _mock_domain()
        domain.create.side_effect = libvirt.libvirtError("no persistent config")
        domain.state.return_value = (libvirt.VIR_DOMAIN_SHUTOFF, 0)
        with pytest.raises(libvirt.libvirtError):
            VmKillFault().revert(domain)
