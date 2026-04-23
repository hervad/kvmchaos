# Running kvmchaos with sudo

Most fault operations (disk.latency, disk.fill, net.*) require root. The recommended
setup avoids running the entire shell as root and ensures run records land in the
invoking user's home directory, not root's.

## Sudoers configuration

Add a drop-in under `/etc/sudoers.d/kvmchaos` (use `visudo -f`):

```
# Allow <user> to run kvmchaos as root without a password.
# SETENV preserves XDG_STATE_HOME so run records go to the user's state dir.
<user> ALL=(root) SETENV: NOPASSWD: /usr/local/bin/kvmchaos, /home/<user>/.local/bin/kvmchaos
```

Replace `<user>` with the operator account (e.g. `kai`).

`SETENV` lets the invoking user pass `XDG_STATE_HOME` through sudo, which takes
precedence over the `SUDO_USER` fallback. Either mechanism writes the run record
to the correct user's `~/.local/state/kvmchaos/runs/` rather than `/root/`.

## Run record directory resolution (priority order)

1. `$XDG_STATE_HOME/kvmchaos/runs/` — if set in the environment
2. `~<SUDO_USER>/.local/state/kvmchaos/runs/` — if running under sudo and `SUDO_USER` resolves
3. `~/.local/state/kvmchaos/runs/` — fallback (current user's home)

## Verifying

After a `sudo kvmchaos inject` run, confirm the record landed in your home:

```bash
ls ~/.local/state/kvmchaos/runs/
```

It should **not** appear under `/root/.local/state/kvmchaos/runs/`.
