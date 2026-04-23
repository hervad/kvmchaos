"""Unit tests for the tc subprocess wrapper."""

from unittest.mock import MagicMock, patch

import pytest

import kvmchaos.tc as tc


class TestAddNetemDelay:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            tc.add_netem_delay("vnet0", 200)
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "replace", "dev", "vnet0", "root", "netem", "delay", "200ms"],
                capture_output=True,
                text=True,
            )

    def test_raises_runtime_error_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="RTNETLINK error")
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.add_netem_delay("vnet0", 200)


class TestDelRootQdisc:
    def test_calls_tc_with_correct_args(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            tc.del_root_qdisc("vnet0")
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "del", "dev", "vnet0", "root"],
                capture_output=True,
                text=True,
            )

    def test_raises_runtime_error_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="RTNETLINK: operation not permitted"
            )
            with pytest.raises(RuntimeError, match="tc command failed"):
                tc.del_root_qdisc("vnet0")

    def test_idempotent_when_no_qdisc_present(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="RTNETLINK answers: No such file or directory"
            )
            tc.del_root_qdisc("vnet0")  # must not raise


class TestShowQdisc:
    def test_returns_stdout(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="qdisc netem 8001: root", stderr=""
            )
            result = tc.show_qdisc("vnet0")
            assert result == "qdisc netem 8001: root"
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "show", "dev", "vnet0"],
                capture_output=True,
                text=True,
            )

    def test_does_not_raise_on_nonzero_exit(self):
        with patch("kvmchaos.tc.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no device")
            result = tc.show_qdisc("vnet0")
            assert result == ""
            mock_run.assert_called_once_with(
                ["tc", "qdisc", "show", "dev", "vnet0"],
                capture_output=True,
                text=True,
            )
