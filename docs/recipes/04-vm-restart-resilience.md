# Recipe 04 — VM Restart Resilience

**Goal:** Verify that a hard VM kill (equivalent to a hypervisor crash)
recovers cleanly — services restart, state replays from WAL, and clients
reconnect.

**Why:** VMs die. Not often, but when they do, you find out whether your
init system, data stores, and client libraries actually handle it.

## Prerequisites

- A VM running the service under test (`app1`)
- The VM is **persistently defined** in libvirt (default for `qemu:///system`)
- Service is configured to start at boot
- Data has been recently written — so we can verify nothing was lost

## Steps

This recipe is **destructive**. Do not run against production unless
you've scoped out the blast radius. Add `app1` to your allowlist first.

1. **Checkpoint state before the kill.**

   Note the newest write ID, the current service version, any open sessions.

2. **Dry run to confirm plan.**

   ```bash
   sudo kvmchaos inject vm.kill app1 --dry-run --yes
   ```

3. **Real kill.** The revert immediately restarts the VM from its defined
   config.

   ```bash
   sudo kvmchaos inject vm.kill app1 --yes --duration 0
   ```

   `--duration 0` means: revert (restart) immediately after the inject.
   Use a longer duration if you want to test multi-minute outages.

4. **Verify recovery after the VM is back up.**
   - SSH or `virsh console` to the VM
   - Service is running (`systemctl status myservice`)
   - Data written before the kill is still there
   - Any replication is catching up, not stalled
   - Clients have reconnected without manual intervention

## Expected outcome

- VM comes back within ~30s (depends on boot time + service startup)
- No committed data is lost
- Clients recover within their configured retry window
- No manual steps required

## Failure modes to watch for

- Service doesn't auto-start (`systemctl enable myservice` missing)
- Data corruption (WAL replay broken — this is a major finding)
- Clients don't reconnect (bad socket error handling)
- Long-running transactions silently lost (no idempotency)
- Network mount doesn't reattach (NFS, iSCSI, shared storage)

## Rate limit

This recipe hits a `vm.kill` — which triggers the destructive rate limit
if configured. If you want to run it repeatedly, set
`min_interval_between_destructive_seconds = 0` temporarily, or pass
`--force`.
