# disk.corrupt Fault — Design Investigation

**Date:** 2026-04-23
**Status:** Deferred — blocked on disk format

## Goal

Add a `disk.corrupt` fault that simulates a failing storage device by injecting
intermittent I/O errors into a VM's disk path, causing the guest to see realistic
block-level failures without permanently damaging the disk image.

## Approach Investigated

**`dm-flakey` device mapper target** — wraps a block device so that a configurable
percentage of I/Os return errors. Fully reversible: removing the dm layer restores
normal I/O. The VM image is never written to.

Inject sequence:
1. Expose the VM disk as a block device via `qemu-nbd`
2. Wrap the nbd device in a `dm-flakey` target
3. Hot-unplug the original disk from the VM via libvirt
4. Hot-plug the dm-flakey device
5. Revert: hot-swap back to original, tear down dm-flakey and nbd

## Why It's Blocked

Lab VMs use **qcow2 disk images**. dm-flakey requires a raw block device to wrap.
Two options were considered:

1. **Direct wrap** — apply dm-flakey to a loop device over the qcow2 file.
   Rejected: dm-flakey would corrupt qcow2 container bytes, not guest sectors,
   silently destroying the image format rather than producing clean I/O errors.

2. **`qemu-nbd` + dm-flakey** — export qcow2 as a block device, wrap in dm-flakey,
   hot-swap via libvirt. Rejected: hot-unplugging the root disk from a running Linux
   guest is unreliable (root filesystem cannot be safely detached while mounted).

## Prerequisites to Unblock

Either of the following would make this feasible:

- **Raw disk images** — convert VM disks from qcow2 to raw format. dm-flakey wraps
  the raw file via a loop device cleanly.
- **Secondary non-root disk** — attach a dedicated raw or qcow2 data disk to the VM.
  `disk.corrupt` targets only that disk. The root disk is never touched, so
  hot-swap is safe.

## Decision

Defer until lab VMs have a secondary non-root disk or are converted to raw format.
Update `PLAN.md` backlog note with this reasoning.
