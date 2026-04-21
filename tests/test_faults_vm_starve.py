"""Tests for vm.starve."""

# test:///default does not implement balloon driver calls (QEMU-specific),
# so all tests use MagicMock(spec=libvirt.virDomain).

from unittest.mock import MagicMock

import libvirt
import pytest

from kvmchaos.faults.vm_starve import VmStarveFault

# maxMemory returns KB; 4 GiB = 4 * 1024 * 1024 KB
_MAX_MEM_KB = 4 * 1024 * 1024  # 4 GiB in KB


class TestVmStarveMetadata:
    def test_name(self):
        assert VmStarveFault.name == "vm.starve"

    def test_description_present(self):
        assert VmStarveFault.description

    def test_non_destructive(self):
        assert VmStarveFault.destructive is False


class TestVmStarveHappyPath:
    def _mock_domain(self, actual_kb: int | None = None) -> MagicMock:
        domain = MagicMock(spec=libvirt.virDomain)
        domain.name.return_value = "testvm"
        domain.maxMemory.return_value = _MAX_MEM_KB
        if actual_kb is None:
            actual_kb = _MAX_MEM_KB // 4  # post-inject state
        domain.memoryStats.return_value = {"actual": actual_kb}
        return domain

    def test_inject_balloons_to_quarter_of_max(self):
        domain = self._mock_domain()
        VmStarveFault().inject(domain)
        domain.setMemory.assert_called_once_with(_MAX_MEM_KB // 4)

    def test_verify_passes_when_memory_is_low(self):
        domain = self._mock_domain(actual_kb=_MAX_MEM_KB // 4)
        VmStarveFault().verify(domain)  # must not raise

    def test_verify_raises_when_memory_still_high(self):
        domain = self._mock_domain(actual_kb=_MAX_MEM_KB)
        with pytest.raises(RuntimeError, match="not starved"):
            VmStarveFault().verify(domain)

    def test_revert_restores_max_memory(self):
        domain = self._mock_domain()
        VmStarveFault().revert(domain)
        domain.setMemory.assert_called_once_with(_MAX_MEM_KB)

    def test_verify_falls_back_to_max_when_actual_absent(self):
        domain = self._mock_domain()
        # memoryStats returns no "actual" key — fallback equals maxMemory(), above threshold
        domain.memoryStats.return_value = {}
        with pytest.raises(RuntimeError, match="not starved"):
            VmStarveFault().verify(domain)


class TestVmStarveErrors:
    def test_inject_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.maxMemory.return_value = _MAX_MEM_KB
        domain.setMemory.side_effect = libvirt.libvirtError("no balloon driver")
        with pytest.raises(libvirt.libvirtError):
            VmStarveFault().inject(domain)

    def test_verify_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.maxMemory.return_value = _MAX_MEM_KB
        domain.memoryStats.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmStarveFault().verify(domain)

    def test_revert_propagates_libvirt_error(self):
        domain = MagicMock(spec=libvirt.virDomain)
        domain.maxMemory.return_value = _MAX_MEM_KB
        domain.setMemory.side_effect = libvirt.libvirtError("boom")
        with pytest.raises(libvirt.libvirtError):
            VmStarveFault().revert(domain)
