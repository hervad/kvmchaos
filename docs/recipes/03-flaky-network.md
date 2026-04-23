# Recipe 03 — Flaky Network

**Goal:** Simulate a degraded WAN link — latency, packet loss, and
bandwidth cap together — to flush out timeout tuning and retry logic.

**Why:** Timeouts are the hardest thing to test. In the lab every
connection is 0.1ms; in the field it's 100-300ms with occasional drops.
Apps that work perfectly in dev often fall over in the first week of
production under realistic network conditions.

## Prerequisites

- A VM running the service under test (`app1`)
- A client that hits the service across the network (synthetic load
  generator or real traffic)
- A latency/error-rate dashboard for the service

## Steps

Run one fault at a time to isolate which tuning you need to fix. Each
inject lasts 180s — long enough to see sustained behaviour, short enough
to back out if alerts go wild.

### 3a. Latency alone

```bash
sudo kvmchaos inject net.latency app1 --yes --duration 180
```

Expected: p50 latency increases by ~200ms (the default delay), p99 by more
if retries pile up. If request rate drops significantly, your client
connection pool is likely too small.

### 3b. Loss alone

```bash
sudo kvmchaos inject net.packet-loss app1 --loss 5 --yes --duration 180
```

Expected: TCP retransmits spike, effective throughput drops. If error
rate on the client side exceeds 5%, the app is surfacing TCP errors to
users instead of retrying transparently.

### 3c. Bandwidth cap alone

```bash
sudo kvmchaos inject net.bandwidth app1 --rate 1024 --yes --duration 180
```

Expected: large responses slow down. If latency alerts fire on anything
other than the cap test, investigate — the app may be blocking callers
unnecessarily.

### 3d. Combined (manual)

kvmchaos can't run multiple net.* faults at once against the same tap
device (they all share the root qdisc). To combine effects, change the
default with custom parameters:

```bash
# Latency + loss together: use tc netem directly for combined faults
# (kvmchaos v0.14 doesn't support combined netem configs yet)
```

## Expected outcome

- Error rate stays below 1% for all three single faults
- Retry logic absorbs the degradation invisibly
- p99 latency stays below your SLO

## Failure modes to watch for

- Connection pool exhaustion (p99 jumps while throughput tanks)
- Retry amplification (loss + retries = dramatically more traffic)
- No backoff on retries (hits downstream even harder during degradation)
- User-visible errors during the 3b test (retry logic missing)
