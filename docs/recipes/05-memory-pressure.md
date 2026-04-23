# Recipe 05 — Memory Pressure

**Goal:** Subject a VM to sustained memory starvation via virtio-balloon,
exposing OOM behaviour, swap thrashing, and GC pathologies.

**Why:** Memory pressure is different from load. A service under CPU load
serves slowly but correctly. A service under memory pressure exhibits
long GC pauses, OOMKiller-triggered restarts, or outright crashes —
often in surprising ways.

## Prerequisites

- A VM with the balloon device enabled (default for most modern libvirt
  domains)
- Monitoring showing VM memory usage and process-level GC metrics
- A workload running on the VM (idle VMs won't show interesting behaviour)

## Steps

1. **Baseline.** Note the VM's current memory usage and your app's
   GC pause time.

   ```bash
   virsh dommemstat app1
   ```

2. **Dry run.**

   ```bash
   kvmchaos inject vm.starve app1 --dry-run --yes
   ```

3. **Real injection.** The fault balloons memory to 25% of the VM's
   configured max, held for 5 minutes.

   ```bash
   kvmchaos inject vm.starve app1 --yes --duration 300
   ```

4. **During the 5 minutes, watch:**
   - Guest memory (`free -h` inside the VM)
   - Swap usage (should go up)
   - App GC pauses (should get longer)
   - Request latency (p99 should spike)
   - OOMKiller log (`dmesg -T | grep -i oom`)

## Expected outcome

- App keeps serving, possibly with higher latency
- Swap absorbs the pressure without hitting OOM
- After revert, memory returns to normal within seconds

## Failure modes to watch for

- **OOMKiller fires** — your app's memory limit is too close to the VM's
  available memory. Tune JVM heap, GOGC, or similar.
- **Swap fills completely** — VM becomes unresponsive. Increase swap size,
  or reduce the starve intensity (but kvmchaos v0.14 doesn't expose the
  balloon percentage as a flag — edit `vm_starve.py` if you need to tune).
- **Cascading failures to other services** — a memory-starved DB can take
  down the app. Isolate via `vm.starve` against non-critical VMs first.

## Safety note

This fault does not kill the VM — it just squeezes RAM. But if the guest
OOMKiller decides to kill your app, you'll need to restart it. The revert
only undoes the balloon; it doesn't revive killed processes.
