"""Tests for kvmchaos.experiment — TOML loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from kvmchaos.experiment import Experiment, Step, load_experiment


class TestLoadExperiment:
    def test_minimal_valid_experiment(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text(
            'name = "t"\n\n[[step]]\nfault = "vm.pause"\nvm = "s1"\n',
        )
        exp = load_experiment(path)
        assert isinstance(exp, Experiment)
        assert exp.name == "t"
        assert exp.description == ""
        assert len(exp.steps) == 1
        assert exp.steps[0] == Step(fault="vm.pause", vm="s1")

    def test_all_fields_parsed(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text(
            'name = "big"\n'
            'description = "does things"\n\n'
            "[[step]]\n"
            'fault = "net.bandwidth"\n'
            'vm = "s1"\n'
            "duration = 60\n"
            "rate = 512\n"
            "continue_on_failure = true\n",
        )
        exp = load_experiment(path)
        assert exp.description == "does things"
        step = exp.steps[0]
        assert step.duration == 60
        assert step.rate == 512
        assert step.continue_on_failure is True

    def test_multiple_steps_in_order(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text(
            'name = "multi"\n\n'
            "[[step]]\n"
            'fault = "vm.pause"\nvm = "a"\n\n'
            "[[step]]\n"
            'fault = "vm.kill"\nvm = "b"\n\n'
            "[[step]]\n"
            'fault = "net.latency"\nvm = "c"\n',
        )
        exp = load_experiment(path)
        assert [s.fault for s in exp.steps] == ["vm.pause", "vm.kill", "net.latency"]
        assert [s.vm for s in exp.steps] == ["a", "b", "c"]

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_experiment(tmp_path / "nope.toml")

    def test_missing_name_raises(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text('[[step]]\nfault = "vm.pause"\nvm = "s1"\n')
        with pytest.raises(ValueError, match="'name'"):
            load_experiment(path)

    def test_no_steps_raises(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n')
        with pytest.raises(ValueError, match=r"\[\[step\]\]"):
            load_experiment(path)

    def test_step_missing_fault_raises(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nvm = "s1"\n')
        with pytest.raises(ValueError, match="missing 'fault'"):
            load_experiment(path)

    def test_step_missing_vm_raises(self, tmp_path: Path):
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nfault = "vm.pause"\n')
        with pytest.raises(ValueError, match="missing 'vm' or 'vms'"):
            load_experiment(path)

    def test_vms_list_in_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "t"\n\n[[step]]\nfault = "vm.pause"\nvms = ["db1", "db2"]\n')
        exp = load_experiment(path)
        assert exp.steps[0].vms == ("db1", "db2")
        assert exp.steps[0].vm == ""

    def test_parallel_flag_in_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "t"\n\n[[step]]\nfault = "vm.pause"\nvm = "s1"\nparallel = true\n')
        exp = load_experiment(path)
        assert exp.steps[0].parallel is True

    def test_step_both_vm_and_vms_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "t"\n\n[[step]]\nfault = "vm.pause"\nvm = "s1"\nvms = ["s2"]\n')
        with pytest.raises(ValueError, match="mutually exclusive"):
            load_experiment(path)

    def test_step_missing_vm_or_vms_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nfault = "vm.pause"\n')
        with pytest.raises(ValueError, match="missing 'vm' or 'vms'"):
            load_experiment(path)


class TestStep:
    def test_vm_normalised_to_vms(self) -> None:
        s = Step(fault="vm.pause", vm="db1")
        assert s.vms == ("db1",)

    def test_vms_accepted_directly(self) -> None:
        s = Step(fault="vm.pause", vms=("db1", "db2"))
        assert s.vms == ("db1", "db2")
        assert s.vm == ""

    def test_both_vm_and_vms_raises(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            Step(fault="vm.pause", vm="db1", vms=("db2",))

    def test_neither_vm_nor_vms_raises(self) -> None:
        with pytest.raises(ValueError, match="required"):
            Step(fault="vm.pause")

    def test_parallel_default_false(self) -> None:
        s = Step(fault="vm.pause", vm="db1")
        assert s.parallel is False

    def test_parallel_set_true(self) -> None:
        s = Step(fault="vm.pause", vm="db1", parallel=True)
        assert s.parallel is True


class TestStepOutcome:
    def test_defaults(self) -> None:
        from kvmchaos.experiment import _StepOutcome

        o = _StepOutcome(vm="server1", success=True)
        assert o.exit_code == 0

    def test_failed_outcome(self) -> None:
        from kvmchaos.experiment import _StepOutcome

        o = _StepOutcome(vm="server1", success=False, exit_code=1)
        assert not o.success
        assert o.exit_code == 1


class TestCollectParallelBatch:
    def _steps(self, parallels: list[bool]) -> list[Step]:
        return [Step(fault="vm.pause", vm=f"s{i}", parallel=p) for i, p in enumerate(parallels)]

    def test_empty_on_non_parallel_step(self) -> None:
        from kvmchaos.experiment import _collect_parallel_batch

        steps = self._steps([False, True])
        assert _collect_parallel_batch(steps, 0) == []

    def test_collects_contiguous_parallel_steps(self) -> None:
        from kvmchaos.experiment import _collect_parallel_batch

        steps = self._steps([True, True, False])
        batch = _collect_parallel_batch(steps, 0)
        assert batch == [(0, steps[0]), (1, steps[1])]

    def test_stops_at_non_parallel(self) -> None:
        from kvmchaos.experiment import _collect_parallel_batch

        steps = self._steps([True, False, True])
        assert len(_collect_parallel_batch(steps, 0)) == 1

    def test_mid_sequence_start(self) -> None:
        from kvmchaos.experiment import _collect_parallel_batch

        steps = self._steps([False, True, True])
        assert len(_collect_parallel_batch(steps, 1)) == 2


class TestStopEventCancellation:
    def test_stop_event_interrupts_hold(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Worker must exit the hold early when the stop event is set."""
        import threading
        import time

        from kvmchaos.cli import _run_experiment_step_on_vm
        from kvmchaos.experiment import Step

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        stop = threading.Event()
        step = Step(fault="vm.pause", vm="test", duration=60)

        # Set stop event after 0.15s — hold should abort well before 60s
        threading.Timer(0.15, stop.set).start()
        t0 = time.monotonic()
        _run_experiment_step_on_vm(
            step,
            "test",
            resolved_uri="test:///default",
            dry_run=False,
            config_path=None,
            force=True,
            stop_event=stop,
        )
        elapsed = time.monotonic() - t0
        assert elapsed < 5, f"hold was not interrupted (took {elapsed:.1f}s)"


class TestLoadExperimentValidation:
    def test_negative_duration_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nfault = "vm.pause"\nvm = "s1"\nduration = -1\n')
        with pytest.raises(ValueError, match="duration"):
            load_experiment(path)

    def test_empty_vms_list_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nfault = "vm.pause"\nvms = []\n')
        with pytest.raises(ValueError, match="vms"):
            load_experiment(path)

    def test_unknown_step_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "e.toml"
        path.write_text('name = "x"\n\n[[step]]\nfault = "vm.pause"\nvm = "s1"\ndurationn = 60\n')
        with pytest.raises(ValueError, match="unknown"):
            load_experiment(path)
