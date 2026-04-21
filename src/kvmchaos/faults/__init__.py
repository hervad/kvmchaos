"""Fault registry.

Maps fault name strings to singleton `Fault` instances.
Adding a fault requires: writing the class, importing it here,
and adding one entry to `FAULTS`. No decorators or entry-point magic.
"""

from __future__ import annotations

from kvmchaos.faults.base import Fault
from kvmchaos.faults.vm_freeze import VmFreezeFault
from kvmchaos.faults.vm_kill import VmKillFault
from kvmchaos.faults.vm_pause import VmPauseFault
from kvmchaos.faults.vm_starve import VmStarveFault

FAULTS: dict[str, Fault] = {
    VmPauseFault.name: VmPauseFault(),
    VmKillFault.name: VmKillFault(),
    VmFreezeFault.name: VmFreezeFault(),
    VmStarveFault.name: VmStarveFault(),
}
