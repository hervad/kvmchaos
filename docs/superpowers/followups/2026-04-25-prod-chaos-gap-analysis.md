# kvmchaos vs production chaos engineering — gap analysis

Date: 2026-04-25
Scope: where kvmchaos sits relative to Chaos Mesh, Litmus, Pumba, ChaosBlade,
Chaos Toolkit, and Gremlin. Recommendations are filtered to ones consistent
with the agent-less single-host minimalist scope; "rewrite as a controller"
is explicitly out.

## 1. Tool-by-tool feature comparison

| Capability                          | Chaos Mesh | Litmus | Pumba | ChaosBlade | Chaos Toolkit | Gremlin | kvmchaos |
|-------------------------------------|------------|--------|-------|------------|---------------|---------|----------|
| Steady-state hypothesis / abort     | partial    | yes    | no    | no         | **yes (core)**| yes     | **no**   |
| HTTP/TCP/script probes              | yes        | yes    | no    | no         | **yes**       | yes     | **no**   |
| Cron / scheduled runs               | **yes (`Schedule` CRD)** | yes | `--interval` only | no | external | yes | **no** |
| Blast-radius % / random subset      | yes (`fixed-percent`, `random-max-percent`) | yes | `--random` | yes | n/a | **yes (`Percent to impact`)** | percent fan-out planned, no random-max-% |
| Restricted time windows             | no         | no     | no    | no         | no            | **yes (Restricted Testing Times)** | **no** |
| RBAC                                | yes (k8s)  | yes (teams) | no | partial   | no            | **yes (RBAC + SAML/OAuth)** | **no** |
| Prometheus metrics                  | yes        | **yes (exporter)** | no | yes (box) | external | yes | **no (out of scope per v0.16 doc)** |
| Webhook / Slack / PagerDuty         | yes        | yes    | no    | yes        | yes (drivers) | yes     | webhook (single) |
| Dashboard / HTML reports            | yes (Dashboard) | yes (ChaosCenter) | no | yes (Box) | journal+report | yes | HTML report |
| Rollback block                      | implicit   | implicit | no  | implicit   | **yes (explicit `rollbacks`)** | implicit | implicit (`revert()`) |
| JVM / app-layer faults              | yes        | yes    | no    | yes        | yes (drivers) | yes     | n/a (agent-less) |
| Kernel / sysrq / panic              | yes (PhysicalMachine) | no | no | yes      | drivers       | yes     | **no** |
| CPU/memory stress                   | yes        | yes    | yes (stress-ng) | yes | drivers      | yes     | **no** |
| Process kill / fork bomb            | yes        | yes    | no    | yes        | drivers       | yes     | partial (`vm.kill` only) |

Sources: chaos-mesh.org/docs (Schedule, PhysicalMachineChaos action list),
litmuschaos.io (Chaos Observability — Prometheus exporter), Pumba README
(commands matrix; netem; stress-ng; `--interval`), ChaosBlade README
(scenario list), chaostoolkit.org (Experiment spec: steady-state-hypothesis,
probes, rollbacks), gremlin.com/docs (Restricted Testing Times, Blast Radius,
RBAC).

## 2. Top 5 missing features for production credibility

1. **Steady-state hypothesis with abort** — Chaos Toolkit's experiment spec
   makes `steady-state-hypothesis` a first-class block re-run before and
   during the method; if a tolerance fails the experiment aborts and rolls
   back. kvmchaos has no equivalent: a misbehaving fault runs the whole
   `duration` regardless of guest health. Concrete shape: a TOML
   `[[probe]]` array (`type=http|tcp|exec`, `url`/`addr`/`cmd`, `tolerance`,
   `interval`) evaluated before run and every N seconds; first failure
   triggers immediate `revert()`.
2. **Cron / scheduled experiments** — Chaos Mesh `Schedule` CRD with a
   standard 5-field cron expression and `concurrencyPolicy`. kvmchaos has
   one-shot only. A `kvmchaos schedule add --cron "..." experiment.toml`
   writing to a state file plus a `kvmchaos schedule run` tick command (or
   systemd-timer recipe) is in scope.
3. **Restricted time windows / safety calendar** — Gremlin's
   "Restricted Testing Times" lets ops teams say "never run 09:00–18:00
   weekdays". kvmchaos already has an allowlist; adding a `[safety]
   forbidden_windows = ["Mon-Fri 09:00-18:00 Europe/Vienna"]` block is a
   small refusal check at run-start.
4. **Probes during the chaos window** — separate from the abort hypothesis,
   Chaos Toolkit's `method` interleaves actions and probes so the run record
   captures evidence ("HTTP 200 at t+5s, 503 at t+12s"). For incident
   reconstruction this turns a kvmchaos run record from "we did X" into
   "we did X and here's what happened". Same probe primitive as #1, just
   recorded into the JSONL stream.
5. **Prometheus exporter** — Litmus's chaos-exporter publishes
   `litmuschaos_experiment_*` series. kvmchaos's v0.16 design explicitly
   listed Prometheus as out-of-scope; that decision is the single biggest
   blocker for "trusted in prod" because SREs cannot alert on stuck reverts
   or run failures from JSONL files. Reopen with a minimal pull endpoint
   exposing run counts, in-flight faults, last-revert-failed gauge.

## 3. Top 3 missing fault types for KVM/libvirt completeness

1. **`vm.cpu_stress` / `vm.mem_stress`** — every comparator ships these
   (Pumba `stress`, Chaos Mesh `stress-cpu`/`stress-mem`, ChaosBlade
   "Basic resources"). Implementation hint: agent-less route is
   `virsh setvcpus --current N` to pin vCPUs and `virsh setmem` to
   balloon-shrink RAM, both fully reversible via libvirt API; no in-guest
   process required. Truly host-side stress is out of agent-less scope.
2. **`vm.reset` / `vm.crash` (forced reboot or QEMU `system_reset`)** —
   distinct from `vm.kill`: simulates a watchdog-triggered reboot, which
   exercises systemd boot ordering and recovery scripts. libvirt:
   `virDomain.reset(0)` (hard reset) and `virDomain.injectNMI()` for
   panic-on-NMI guests. Chaos Mesh PhysicalMachineChaos exposes both.
3. **`disk.detach` / `net.detach` (hot-unplug)** — exercises hotplug-loss
   paths that timeouts can't reach. libvirt:
   `virDomain.detachDeviceFlags(xml, VIR_DOMAIN_AFFECT_LIVE)` against a
   target disk or NIC, with `attachDeviceFlags` on revert. Closer in spirit
   to Gremlin's "Shutdown/Blackhole" than to netem-style perturbation.

## Notes on what NOT to add

- No multi-host orchestrator. Spec says single-host; that's a feature,
  not a gap.
- No web dashboard. HTML report is sufficient; live UI would drag in
  daemon mode which is explicitly non-goal.
- No application-layer faults (JVM, HTTP mutate). Requires an agent;
  PLAN.md already disclaims this.
- No RBAC system. Single-host CLI run by an admin; libvirt group + the
  existing `--i-understand-this-breaks-things` flag is the right level.
  An audit-trail strengthening (signed run records, append-only log) is
  in scope and cheaper than RBAC.
