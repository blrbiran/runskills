# Systemd Service Optimization Checklist

## 1) Baseline First

- Collect `systemctl status`, `systemctl cat`, `systemctl show`, and boot logs.
- Record current startup timing (`systemd-analyze critical-chain <unit>`).
- Record restart history and failure signatures (`journalctl -u <unit> -b`).

## 2) Dependency Hygiene

- Remove unnecessary `After=`, `Wants=`, and `Requires=`.
- Keep only dependencies that are strictly required at startup.
- Verify no dependency cycle is introduced.

## 3) Startup Path

- Minimize work in `ExecStartPre=`.
- Avoid long-running shell wrappers for `ExecStart=`.
- Move optional initialization to separate oneshot units if needed.

## 4) Restart Behavior

- Use `Restart=on-failure` for most long-running daemons.
- Set non-zero `RestartSec=` to avoid hot restart loops.
- Configure `StartLimitIntervalSec=` and `StartLimitBurst=` for unstable services.

## 5) Resource Controls

- Enable accounting only if metrics are needed.
- Set `MemoryMax=` with headroom and observe OOM events.
- Set `CPUQuota=` conservatively; avoid starving latency-sensitive services.
- Review `TasksMax=` for thread-heavy workloads.

## 6) Change Safety

- Use drop-in overrides in `/etc/systemd/system/<unit>.d/override.conf`.
- Never edit vendor unit files directly.
- Apply one change group at a time and validate immediately.
- Keep rollback command sequence ready (`daemon-reload`, restart, verify).

## 7) Post-change Validation

- Confirm active/running status and health endpoint behavior.
- Compare boot/runtime metrics against baseline.
- Re-check logs for new warnings caused by hardening or limits.
