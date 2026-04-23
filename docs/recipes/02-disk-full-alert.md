# Recipe 02 — Disk-Full Alert Validation

**Goal:** Confirm the low-disk monitoring alert fires with enough lead time
for operations to intervene before the VM runs out of space.

**Why:** ENOSPC is a leading cause of silent data loss and weird
application behaviour. An alert that fires at 99.9% full is too late.

## Prerequisites

- A non-production VM with its backing qcow2 on the KVM host's filesystem
- Monitoring configured with a low-disk threshold (typical: 85% or 90%)
- You know the free space on the host filesystem (`df -h` on host)

## Steps

1. **Dry run.**

   ```bash
   sudo kvmchaos inject disk.fill server1 --size 10240 --dry-run --yes
   ```

2. **Fill 10 GiB next to the VM image.** This triggers ENOSPC from the
   host's perspective when the VM tries to write.

   ```bash
   sudo kvmchaos inject disk.fill server1 --size 10240 --yes --duration 180
   ```

3. **Watch the alert pipeline.** During the 180s hold:
   - Host free space: should drop by ~10 GiB (`df -h`)
   - VM I/O: writes should slow or fail
   - Monitoring: low-disk alert should trigger

4. **Revert.** The fill file is removed automatically when the hold expires.

## Expected outcome

- Alert fires within one monitoring cycle of crossing the threshold
- VM stays up (no kernel panic — ENOSPC is handled by most filesystems)
- After revert, free space returns to baseline

## Failure modes to watch for

- Alert takes >2 monitoring cycles to fire (rate limiting or suppression)
- Alert fires at 99% instead of 85% (threshold too high)
- No paging (alert defined but not routed)
- Alert recovers before a human acknowledges it (flapping)

## Tuning

Adjust `--size` to overshoot the alert threshold by a known margin.
Example: if free space is 50 GiB and the alert is set at 80% used,
you need to fill ~40 GiB to cross the threshold.
