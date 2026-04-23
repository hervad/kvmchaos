# Recipe 01 — Database Failover

**Goal:** Verify that the application layer fails over cleanly when the
primary database VM loses network connectivity.

**Why:** The automated failover path is the most common source of "it works
on paper" incidents. If the app waits 30s before giving up on the primary,
you'll see a 30s outage rather than a graceful degradation.

## Prerequisites

- Two VMs: `db-primary`, `db-replica`
- An application VM or external client that connects to the DB
- Replication healthy before the test (`repl_lag == 0`)
- A dashboard or log tail showing which DB is active

## Steps

1. **Baseline.** Confirm the app reaches `db-primary` normally.

   ```bash
   kvmchaos list-vms | grep db-
   ```

2. **Dry run first.**

   ```bash
   sudo kvmchaos inject net.partition db-primary --dry-run --yes --duration 60
   ```

   The run record should show `dry_run: true` and `outcome: dry_run`.

3. **Real injection.** Partition the primary for 60 seconds.

   ```bash
   sudo kvmchaos inject net.partition db-primary --yes --duration 60
   ```

   During the 60s hold, watch for:
   - App logs: connection errors to primary, then reconnection to replica
   - DB proxy: failover promotion of replica
   - Your metrics: error rate spike, then recovery

4. **After revert.** Confirm the primary rejoins as a replica (or is
   demoted per your topology) and replication catches up.

## Expected outcome

- App error rate spikes within ~5s of partition
- Failover promotion completes within your SLO (typical: 15-30s)
- No user-visible errors after the failover completes
- After revert, the primary rejoins without manual intervention

## Failure modes to watch for

- App times out on TCP connect instead of failing fast (pool sizing / keepalive)
- Proxy doesn't detect the outage (healthcheck interval too high)
- Replica promotion requires manual approval (automation gap)
- Replication lag prevents promotion (run a separate capacity test)

## Cleanup if something goes wrong

```bash
sudo kvmchaos abort-all --yes
```
