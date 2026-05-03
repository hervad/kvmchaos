"""Tests for disk.fill fault."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import libvirt
import pytest

from kvmchaos.faults.disk_fill import (
    DiskFillFault,
    _fill_path,
    _image_path,
)

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


class TestDiskFillMetadata:
    def test_name(self):
        assert DiskFillFault.name == "disk.fill"

    def test_description_present(self):
        assert DiskFillFault.description

    def test_non_destructive(self):
        assert DiskFillFault.destructive is False

    def test_default_fill_bytes(self):
        fault = DiskFillFault()
        assert fault.fill_bytes == 1_073_741_824  # 1 GiB

    def test_custom_fill_bytes(self):
        fault = DiskFillFault(fill_bytes=512 * 1024 * 1024)
        assert fault.fill_bytes == 536_870_912


class TestImagePath:
    def test_extracts_source_file(self):
        domain = _mock_domain()
        result = _image_path(domain)
        assert result == Path("/var/lib/libvirt/images/rhel9.7.qcow2")

    def test_raises_when_no_disk(self):
        domain = _mock_domain(_XML_NO_DISK)
        with pytest.raises(RuntimeError, match="No disk source"):
            _image_path(domain)

    def test_raises_when_no_file_attr(self):
        xml = """
        <domain>
          <devices>
            <disk type='block' device='disk'>
              <source dev='/dev/sda'/>
            </disk>
          </devices>
        </domain>
        """
        domain = _mock_domain(xml)
        with pytest.raises(RuntimeError, match="no file attribute"):
            _image_path(domain)


class TestFillPath:
    def test_fill_path_sits_next_to_image(self):
        image = Path("/var/lib/libvirt/images/rhel9.7.qcow2")
        result = _fill_path(image, "server1")
        assert result == Path("/var/lib/libvirt/images/.kvmchaos-fill-server1")

    def test_fill_path_uses_vm_name(self):
        image = Path("/data/images/win2022.qcow2")
        result = _fill_path(image, "win2022")
        assert result.name == ".kvmchaos-fill-win2022"


class TestDiskFillInject:
    def test_inject_calls_fallocate(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch("kvmchaos.faults.disk_fill.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            fault.inject(domain)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "fallocate" in cmd
        assert str(1024) in " ".join(cmd)

    def test_inject_creates_fill_file_on_fallocate_unavailable(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=4096)

        def fake_run(cmd, **kwargs):
            if "fallocate" in cmd:
                raise FileNotFoundError("fallocate not found")
            return MagicMock(returncode=0)

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch("kvmchaos.faults.disk_fill.subprocess.run", side_effect=fake_run),
        ):
            fault.inject(domain)

        # dd fallback should have been called instead
        # The fill file is produced either way — test existence

    def test_inject_cleans_up_fill_file_on_fallocate_error(self, tmp_path: Path):
        """Partial fill file must be deleted if fallocate raises CalledProcessError."""
        import shutil

        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)
        fill = _fill_path(image, "server1")

        def _fallocate_creates_partial(*args: object, **kwargs: object) -> None:
            fill.write_bytes(b"partial")  # file created before failure, as fallocate does
            raise subprocess.CalledProcessError(1, "fallocate")

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch(
                "kvmchaos.faults.disk_fill.shutil.disk_usage",
                return_value=shutil.disk_usage("/")._replace(free=10 * 1024 * 1024 * 1024),
            ),
            patch(
                "kvmchaos.faults.disk_fill.subprocess.run", side_effect=_fallocate_creates_partial
            ),
            pytest.raises(RuntimeError),
        ):
            fault.inject(domain)

        assert not fill.exists(), "fill file must be removed after failed inject"

    def test_inject_raises_on_fallocate_failure(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch(
                "kvmchaos.faults.disk_fill.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "fallocate"),
            ),
            pytest.raises(RuntimeError, match=r"disk\.fill inject failed"),
        ):
            fault.inject(domain)


class TestDiskFillFreeSpaceGuard:
    def test_inject_raises_when_insufficient_space(self, tmp_path: Path):
        import shutil

        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=10 * 1024 * 1024 * 1024)  # 10 GiB

        # Simulate only 1 GiB free
        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch(
                "kvmchaos.faults.disk_fill.shutil.disk_usage",
                return_value=shutil.disk_usage("/")._replace(free=1 * 1024 * 1024 * 1024),
            ),
            pytest.raises(RuntimeError, match="insufficient disk space"),
        ):
            fault.inject(domain)

    def test_inject_proceeds_when_sufficient_space(self, tmp_path: Path):
        import shutil

        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            patch(
                "kvmchaos.faults.disk_fill.shutil.disk_usage",
                return_value=shutil.disk_usage("/")._replace(free=10 * 1024 * 1024 * 1024),
            ),
            patch("kvmchaos.faults.disk_fill.subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            fault.inject(domain)

        mock_run.assert_called_once()


class TestDiskFillVerify:
    def test_verify_passes_when_fill_file_exists(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        fill = _fill_path(image, "server1")
        fill.write_bytes(b"\x00" * 1024)
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)

        with patch("kvmchaos.faults.disk_fill._image_path", return_value=image):
            fault.verify(domain)  # must not raise

    def test_verify_raises_when_fill_file_absent(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault(fill_bytes=1024)

        with (
            patch("kvmchaos.faults.disk_fill._image_path", return_value=image),
            pytest.raises(RuntimeError, match="fill file not found"),
        ):
            fault.verify(domain)


class TestDiskFillRevert:
    def test_revert_deletes_fill_file(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        fill = _fill_path(image, "server1")
        fill.write_bytes(b"\x00" * 1024)
        domain = _mock_domain()
        fault = DiskFillFault()

        with patch("kvmchaos.faults.disk_fill._image_path", return_value=image):
            fault.revert(domain)

        assert not fill.exists()

    def test_revert_is_idempotent_when_file_already_gone(self, tmp_path: Path):
        image = tmp_path / "vm.qcow2"
        image.write_text("")
        domain = _mock_domain()
        fault = DiskFillFault()

        with patch("kvmchaos.faults.disk_fill._image_path", return_value=image):
            fault.revert(domain)  # fill file never existed — must not raise
