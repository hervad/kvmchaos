# kvmchaos Recipes

Worked examples of common chaos engineering scenarios. Each recipe states
what it tests, what you need, the exact commands to run, and what a
successful outcome looks like.

| Recipe | Purpose |
|---|---|
| [01-database-failover](01-database-failover.md) | Verify the app fails over when the primary DB loses network |
| [02-disk-full-alert](02-disk-full-alert.md) | Confirm the low-disk alert fires before the VM runs out of space |
| [03-flaky-network](03-flaky-network.md) | Simulate a slow, lossy WAN link |
| [04-vm-restart-resilience](04-vm-restart-resilience.md) | Test service recovery after a VM is force-killed |
| [05-memory-pressure](05-memory-pressure.md) | Stress a VM under sustained memory starvation |

## General guidance

- Run every experiment in **dry-run mode first** (`--dry-run`). The run record
  will show the planned steps; no libvirt calls happen.
- Keep your **allowlist** tight. `docs/examples/config.toml` shows a complete
  template.
- If a revert fails mid-run and leaves a VM stuck, `kvmchaos abort-all` will
  clear any active `net.*` qdiscs across the host.
- Open a second terminal tailing the VM's journal (or your app log) while the
  experiment runs. A run record tells you *what kvmchaos did*; your logs tell
  you *how the system responded*.
