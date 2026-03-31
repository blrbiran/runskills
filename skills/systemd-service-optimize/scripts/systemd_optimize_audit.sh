#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") <unit-name> [output-dir]

Examples:
  $(basename "$0") nginx.service
  $(basename "$0") docker.service /tmp/docker-audit
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" || $# -lt 1 ]]; then
  usage
  exit $([[ $# -lt 1 ]] && echo 1 || echo 0)
fi

unit="$1"
shift || true

safe_unit="${unit//[^a-zA-Z0-9_.@-]/_}"
timestamp="$(date +%Y%m%d-%H%M%S)"
out_dir="${1:-./systemd-audit-${safe_unit}-${timestamp}}"
mkdir -p "$out_dir"

run_capture() {
  local name="$1"
  shift
  {
    echo "$ $*"
    "$@"
  } >"${out_dir}/${name}.txt" 2>&1 || true
}

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found. Run on a system with systemd." >&2
  exit 2
fi

if ! systemctl show "$unit" >/dev/null 2>&1; then
  echo "Unit not found or inaccessible: $unit" >&2
  exit 3
fi

run_capture status systemctl status "$unit" --no-pager
run_capture cat systemctl cat "$unit"
run_capture show-core systemctl show "$unit" \
  -p Id -p Description -p Type -p MainPID -p SubState -p ActiveState \
  -p Restart -p RestartSec -p TimeoutStartUSec -p TimeoutStopUSec \
  -p CPUAccounting -p CPUQuotaPerSecUSec -p MemoryAccounting -p MemoryMax \
  -p IOAccounting -p IOWeight -p TasksAccounting -p TasksMax \
  -p FragmentPath -p DropInPaths
run_capture logs-current-boot journalctl -u "$unit" -b --no-pager -n 400
run_capture deps systemctl list-dependencies "$unit"
run_capture reverse-deps systemctl list-dependencies --reverse "$unit"

if command -v systemd-analyze >/dev/null 2>&1; then
  run_capture critical-chain systemd-analyze critical-chain "$unit"
  run_capture blame systemd-analyze blame

  frag_path="$(systemctl show "$unit" -p FragmentPath --value || true)"
  if [[ -n "$frag_path" && -f "$frag_path" ]]; then
    run_capture verify-fragment systemd-analyze verify "$frag_path"
  fi

  if systemd-analyze --help 2>/dev/null | grep -q "security"; then
    run_capture security systemd-analyze security "$unit"
  fi
fi

{
  echo "# Systemd Audit Summary"
  echo
  echo "- Unit: \\`$unit\\`"
  echo "- Timestamp: \\`$timestamp\\`"
  echo "- Output directory: \\`$out_dir\\`"
  echo
  echo "## Key Properties"
  echo
  awk -F= '
    /^Type=|^Restart=|^RestartSec=|^TimeoutStartUSec=|^TimeoutStopUSec=|^CPUAccounting=|^CPUQuotaPerSecUSec=|^MemoryAccounting=|^MemoryMax=|^TasksAccounting=|^TasksMax=|^IOAccounting=|^IOWeight=|^FragmentPath=|^DropInPaths=/ {
      printf("- %s: `%s`\\n", $1, $2)
    }
  ' "${out_dir}/show-core.txt"
  echo
  echo "## Next Step"
  echo
  echo "Review critical-chain, logs-current-boot, and show-core first. Apply one drop-in change at a time, then re-run this audit for before/after comparison."
} >"${out_dir}/SUMMARY.md"

echo "Audit complete: ${out_dir}"
echo "Open: ${out_dir}/SUMMARY.md"
