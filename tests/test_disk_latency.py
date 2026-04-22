"""Tests for disk.latency fault."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import libvirt
import pytest

from kvmchaos.faults.disk_latency import DiskLatencyFault

_XML = """
<domain>
  <devices>
    <disk type='file' device='disk'>
      <source file='/var/lib/libvirt/images/rhel9.7.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""

_XML_NO_DISK = "<domain><devices></devices></domain>"


def _mock_domain(xml: str = _XML) -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = "server1"
    domain.XMLDesc.return_value = xml
    return domain


class TestDiskLatencyMetadata:
    def test_name(self):
        assert DiskLatencyFault.name == "disk.latency"

    def test_description_present(self):
        assert DiskLatencyFault.description

    def test_non_destructive(self):
        assert DiskLatencyFault.destructive is False

    def test_local_only(self):
        assert DiskLatencyFault.local_only is True

    def test_default_bandwidth(self):
        fault = DiskLatencyFault()
        assert fault.bandwidth_bps == 1_000_000

    def test_custom_bandwidth(self):
        fault = DiskLatencyFault(bandwidth_bps=2_000_000)
        assert fault.bandwidth_bps == 2_000_000


def _make_stat(major: int, minor: int) -> os.stat_result:
    """Build a fake stat_result with the given device major:minor."""
    fake = MagicMock(spec=os.stat_result)
    fake.st_dev = os.makedev(major, minor)
    return fake


class TestDiskLatencyInject:
    def test_inject_writes_correct_io_max(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.inject(domain)

        assert io_max.read_text() == "8:0 rbps=1000000 wbps=1000000\n"

    def test_inject_uses_custom_bandwidth(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=2_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.inject(domain)

        assert "rbps=2000000 wbps=2000000" in io_max.read_text()


class TestDiskLatencyVerify:
    def test_verify_passes_when_limit_set(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=1000000 wbps=1000000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.verify(domain)  # must not raise

    def test_verify_raises_when_limit_absent(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=max wbps=max\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
            pytest.raises(RuntimeError, match="not in effect"),
        ):
            fault.verify(domain)

    def test_verify_raises_when_bandwidth_differs(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=500000 wbps=500000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault(bandwidth_bps=1_000_000)

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
            pytest.raises(RuntimeError),
        ):
            fault.verify(domain)


class TestDiskLatencyRevert:
    def test_revert_writes_max(self, tmp_path: Path):
        io_max = tmp_path / "io.max"
        io_max.write_text("8:0 rbps=1000000 wbps=1000000\n")
        domain = _mock_domain()
        fault = DiskLatencyFault()

        with (
            patch("kvmchaos.faults.disk_latency._io_max_path", return_value=io_max),
            patch("kvmchaos.faults.disk_latency._disk_dev", return_value=(8, 0)),
        ):
            fault.revert(domain)

        assert io_max.read_text() == "8:0 rbps=max wbps=max\n"


class TestDiskLatencyHelpers:
    def test_qemu_pid_raises_when_not_running(self, tmp_path: Path):
        with patch(
            "kvmchaos.faults.disk_latency.Path",
            side_effect=FileNotFoundError("no pid file"),
        ):
            from kvmchaos.faults.disk_latency import _qemu_pid

            with pytest.raises(FileNotFoundError):
                _qemu_pid("missing-vm")

    def test_disk_dev_parses_xml(self):
        domain = _mock_domain()
        fake_stat = _make_stat(8, 0)
        with patch("kvmchaos.faults.disk_latency.os.stat", return_value=fake_stat):
            from kvmchaos.faults.disk_latency import _disk_dev

            major, minor = _disk_dev(domain)
        assert major == 8
        assert minor == 0

    def test_disk_dev_raises_when_no_disk(self):
        domain = _mock_domain(_XML_NO_DISK)
        from kvmchaos.faults.disk_latency import _disk_dev

        with pytest.raises(RuntimeError, match="No disk source"):
            _disk_dev(domain)
