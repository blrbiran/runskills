---
name: systemd-service-optimize
description: Optimize Linux systemd services for faster startup, higher reliability, and lower resource usage. Use when working with .service/.socket/.timer units, diagnosing slow boot or restart loops, tuning cgroup resource controls, or generating safe drop-in overrides under /etc/systemd/system/unit-name.d/.
---

# Systemd Service Optimize

## Outcome

Produce a safe, testable optimization plan for a target systemd unit and apply only minimal, reversible overrides.

## Workflow

1. Establish a baseline.
- Confirm unit existence: `systemctl status <unit>`.
- Capture current unit definition: `systemctl cat <unit>`.
- Capture runtime properties: `systemctl show <unit>`.
- Capture logs from current boot: `journalctl -u <unit> -b --no-pager`.
- Run bundled audit script: `./scripts/systemd_optimize_audit.sh <unit> [output_dir]`.

2. Identify the primary bottleneck before editing.
- Prioritize startup path issues: dependency chain, blocking `ExecStartPre`, DNS/network waits, storage waits.
- Prioritize restart instability: crash loops, too-aggressive `RestartSec`, timeout mismatch, missing dependencies.
- Prioritize resource pressure: CPU throttling, memory ceiling, too-low `TasksMax`, heavy I/O contention.

3. Choose the smallest effective override.
- Prefer drop-ins under `/etc/systemd/system/<unit>.d/override.conf`.
- Do not edit vendor unit files in `/usr/lib/systemd/system` or `/lib/systemd/system`.
- Apply one optimization group at a time (dependency, startup command, restart policy, resource controls).

4. Validate after each change.
- Reload daemon: `systemctl daemon-reload`.
- Restart or reload unit as appropriate.
- Verify active state and logs.
- Compare startup timing and failure rate against baseline artifacts.

5. Keep rollback trivial.
- Remove only the added drop-in file or section.
- Reload daemon and restart unit.
- Re-check health and logs.

## Optimization Playbook

### Startup latency

- Remove unnecessary ordering dependencies (`After=`, `Wants=`, `Requires=`).
- Move non-critical waits out of `ExecStartPre=`.
- Use socket activation when applicable.
- Replace long shell wrappers with direct binaries where possible.

### Reliability

- Align `Restart=` policy with failure mode.
- Set reasonable `RestartSec=` to prevent hot loops.
- Tune `TimeoutStartSec=` and `TimeoutStopSec=` to real workload behavior.
- Add `StartLimitIntervalSec=` and `StartLimitBurst=` safeguards for unstable workloads.

### Resource efficiency

- Enable accounting when needed (`CPUAccounting=`, `MemoryAccounting=`, `IOAccounting=`).
- Set conservative limits with evidence (`CPUQuota=`, `MemoryMax=`, `TasksMax=`, `IOWeight=`).
- Avoid limits that induce thrashing or OOM kill loops.

### Security-hardening side effects

- Re-check behavior after hardening directives (`ProtectSystem=`, `PrivateTmp=`, `NoNewPrivileges=`, `CapabilityBoundingSet=`).
- Confirm service still accesses required paths, sockets, and capabilities.

## Apply Pattern

Create or update drop-in:

```bash
sudo mkdir -p /etc/systemd/system/<unit>.d
sudoedit /etc/systemd/system/<unit>.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart <unit>
systemctl status <unit> --no-pager
```

Use section reset semantics when replacing list-type directives:

```ini
[Unit]
After=
After=network-online.target

[Service]
ExecStart=
ExecStart=/usr/local/bin/my-service --config /etc/my-service/config.yaml
Restart=on-failure
RestartSec=5s
```

## Bundled Resources

- `scripts/systemd_optimize_audit.sh`: Collect diagnostic snapshots and baseline artifacts for one unit.
- `scripts/convert_systemd_docs_to_md.py`: Convert locally-downloaded systemd HTML manpages in `doc/` into clean Markdown reference files.
- `references/optimization-checklist.md`: Fast checklist of common, safe optimization decisions.
- `references/systemd-manpages/*.md`: Converted official systemd manpages for targeted lookup during optimization tasks.

## Reference Routing

- Read `references/systemd-manpages/systemd.service.md` when tuning service lifecycle, `Type=`, restart flow, and `Exec*=` behavior.
- Read `references/systemd-manpages/systemd.exec.md` when tuning sandboxing, environment, `WorkingDirectory=`, capability, and namespace options.
- Read `references/systemd-manpages/systemd.resource-control.md` when setting `CPUQuota=`, `MemoryMax=`, `TasksMax=`, I/O limits, and slice behavior.
- Read `references/systemd-manpages/systemd.unit.md` when debugging ordering/dependency graphs (`After=`, `Wants=`, `Requires=`).
- Read `references/systemd-manpages/systemd.kill.md` when stop/reload semantics or signal behavior is involved.
- Read `references/systemd-manpages/systemd.socket.md` and `systemd.timer.md` for socket activation and timer-triggered service patterns.
