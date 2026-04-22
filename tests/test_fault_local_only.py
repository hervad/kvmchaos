"""Tests that all registered faults expose the local_only attribute correctly."""

from __future__ import annotations

import pytest

from kvmchaos.faults import FAULTS
from kvmchaos.faults.net_latency import NetLatencyFault
from kvmchaos.faults.vm_freeze import VmFreezeFault
from kvmchaos.faults.vm_kill import VmKillFault
from kvmchaos.faults.vm_pause import VmPauseFault
from kvmchaos.faults.vm_starve import VmStarveFault


@pytest.mark.parametrize("name,fault", list(FAULTS.items()))
def test_all_faults_have_local_only(name: str, fault: object) -> None:
    assert hasattr(fault, "local_only"), f"{name} missing local_only"
    assert isinstance(fault.local_only, bool)


def test_net_latency_is_local_only() -> None:
    assert NetLatencyFault.local_only is True


@pytest.mark.parametrize("cls", [VmPauseFault, VmKillFault, VmFreezeFault, VmStarveFault])
def test_vm_faults_are_not_local_only(cls: type) -> None:
    assert cls.local_only is False


class TestLocalOnlyAttribute:
    def test_disk_latency_is_local_only(self) -> None:
        from kvmchaos.faults import FAULTS

        assert FAULTS["disk.latency"].local_only is True
