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
