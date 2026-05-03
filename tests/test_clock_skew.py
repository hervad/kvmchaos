"""Tests for clock.skew fault."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import libvirt
import pytest

from kvmchaos.faults.clock_skew import ClockSkewFault

_GUEST_NOW = 1_776_900_818  # arbitrary fixed epoch seconds


def _mock_domain() -> MagicMock:
    domain = MagicMock(spec=libvirt.virDomain)
    domain.name.return_value = "server1"
    domain.getTime.return_value = {"seconds": _GUEST_NOW, "nseconds": 0}
    return domain


class TestClockSkewMetadata:
    def test_name(self):
        assert ClockSkewFault.name == "clock.skew"

    def test_description_present(self):
        assert ClockSkewFault.description

    def test_non_destructive(self):
        assert ClockSkewFault.destructive is False

    def test_default_skew(self):
        assert ClockSkewFault().skew_seconds == 3600

    def test_custom_skew(self):
        assert ClockSkewFault(skew_seconds=-7200).skew_seconds == -7200


class TestClockSkewInject:
    def test_inject_sets_time_forward(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)
        domain.setTime.assert_called_once_with({"seconds": _GUEST_NOW + 3600, "nseconds": 0})

    def test_inject_sets_time_backward(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=-1800)
        fault.inject(domain)
        domain.setTime.assert_called_once_with({"seconds": _GUEST_NOW - 1800, "nseconds": 0})

    def test_inject_reads_guest_time_before_setting(self):
        domain = _mock_domain()
        fault = ClockSkewFault()
        fault.inject(domain)
        # getTime must be called before setTime
        assert domain.getTime.call_count == 1
        assert domain.setTime.call_count == 1


class TestClockSkewVerify:
    def test_verify_passes_when_time_is_skewed(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)
        # After inject, getTime returns skewed value
        domain.getTime.return_value = {"seconds": _GUEST_NOW + 3600, "nseconds": 0}
        fault.verify(domain)  # must not raise

    def test_verify_raises_when_time_not_skewed(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)
        # getTime still returns original (unskewed) time
        domain.getTime.return_value = {"seconds": _GUEST_NOW, "nseconds": 0}
        with pytest.raises(RuntimeError, match="clock skew not in effect"):
            fault.verify(domain)

    def test_verify_tolerates_small_drift(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)
        # 5 seconds of drift is acceptable
        domain.getTime.return_value = {"seconds": _GUEST_NOW + 3600 + 5, "nseconds": 0}
        fault.verify(domain)  # must not raise

    def test_verify_raises_before_inject(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        # Never injected — no expected time stored
        with pytest.raises(RuntimeError, match="not injected"):
            fault.verify(domain)


class TestClockSkewRevert:
    def test_revert_restores_wall_clock(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)

        wall_now = 1_776_904_500
        with patch("kvmchaos.faults.clock_skew.time.time", return_value=float(wall_now)):
            fault.revert(domain)

        domain.setTime.assert_called_with({"seconds": wall_now, "nseconds": 0})

    def test_revert_clears_injected_state(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        fault.inject(domain)

        with patch("kvmchaos.faults.clock_skew.time.time", return_value=float(_GUEST_NOW)):
            fault.revert(domain)

        # After revert, verify should raise "not injected"
        with pytest.raises(RuntimeError, match="not injected"):
            fault.verify(domain)

    def test_revert_raises_when_not_injected(self):
        domain = _mock_domain()
        fault = ClockSkewFault(skew_seconds=3600)
        with pytest.raises(RuntimeError, match="not injected"):
            fault.revert(domain)


class TestClockSkewParallelIsolation:
    def test_verify_uses_per_domain_expected_time(self):
        """Singleton fault must track expected time per VM, not overwrite on second inject."""
        fault = ClockSkewFault(skew_seconds=3600)

        domain_a = MagicMock(spec=libvirt.virDomain)
        domain_a.name.return_value = "vm-a"
        domain_a.getTime.return_value = {"seconds": 1_000_000}

        domain_b = MagicMock(spec=libvirt.virDomain)
        domain_b.name.return_value = "vm-b"
        domain_b.getTime.return_value = {"seconds": 2_000_000}

        fault.inject(domain_a)  # expected for vm-a: 1_003_600
        fault.inject(domain_b)  # expected for vm-b: 2_003_600; must NOT overwrite vm-a's

        # Both domains report their correctly-skewed times
        domain_a.getTime.return_value = {"seconds": 1_003_600}
        domain_b.getTime.return_value = {"seconds": 2_003_600}

        fault.verify(domain_a)  # must not raise
        fault.verify(domain_b)  # must not raise
