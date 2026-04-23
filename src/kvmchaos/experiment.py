"""TOML-based experiment runner.

An experiment is a sequence of ``inject`` steps executed in order. Each step
runs the full inject → verify → hold → revert lifecycle before the next
step begins. A step failure stops the experiment unless the step opts in
to ``continue_on_failure``.

Example ``experiment.toml``::

    name = "db-failover-drill"
    description = "Partition primary, watch app fail over, restore."

    [[step]]
    fault = "net.partition"
    vm = "db-primary"
    duration = 60

    [[step]]
    fault = "vm.pause"
    vm = "db-primary"
    duration = 30
    continue_on_failure = true

Experiments are not transactional: if step 3 of 5 fails, steps 1-2 already
ran. Revert semantics are per-step (each fault reverts itself after its
hold), so there is no global "roll back" to undo completed steps.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Step:
    """One step in an experiment. Mirrors ``kvmchaos inject`` CLI flags."""

    fault: str
    vm: str
    duration: int = 20
    bandwidth: int = 1
    size: int = 1024
    loss: int = 10
    rate: int = 1000
    corrupt: int = 1
    skew: int = 3600
    continue_on_failure: bool = False


@dataclass(frozen=True)
class Experiment:
    """A named sequence of inject steps."""

    name: str
    description: str = ""
    steps: tuple[Step, ...] = field(default_factory=tuple)


def load_experiment(path: Path) -> Experiment:
    """Parse a TOML experiment file into an :class:`Experiment`.

    Args:
        path: Path to a TOML experiment file.

    Returns:
        Parsed :class:`Experiment`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is missing required fields.
        tomllib.TOMLDecodeError: If the TOML is malformed.
    """
    if not path.is_file():
        raise FileNotFoundError(f"experiment file not found: {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise ValueError(f"experiment {path}: missing top-level 'name' field")

    raw_steps = data.get("step", [])
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(f"experiment {path}: at least one [[step]] table required")

    steps: list[Step] = []
    for i, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"experiment {path}: step {i} is not a table")
        if "fault" not in raw:
            raise ValueError(f"experiment {path}: step {i} missing 'fault'")
        if "vm" not in raw:
            raise ValueError(f"experiment {path}: step {i} missing 'vm'")
        steps.append(
            Step(
                fault=str(raw["fault"]),
                vm=str(raw["vm"]),
                duration=int(raw.get("duration", 20)),
                bandwidth=int(raw.get("bandwidth", 1)),
                size=int(raw.get("size", 1024)),
                loss=int(raw.get("loss", 10)),
                rate=int(raw.get("rate", 1000)),
                corrupt=int(raw.get("corrupt", 1)),
                skew=int(raw.get("skew", 3600)),
                continue_on_failure=bool(raw.get("continue_on_failure", False)),
            )
        )

    return Experiment(
        name=str(name),
        description=str(data.get("description", "")),
        steps=tuple(steps),
    )
