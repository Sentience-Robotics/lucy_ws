#!/usr/bin/env bash
# Exit 0 when ros2_control reports at least one *active* controller.
#
#   scripts/controllers_active.sh [min_active]
#
# Used by config/launcher_config.json so core reads ready only when the robot can
# actually be driven. Process liveness is not enough: controller_manager happily
# runs with every controller stuck `unconfigured`/`inactive` — which is exactly
# what a stale /robot_description or a held spawner lock produces — and the TUI
# would otherwise show a green [RUNNING] next to a robot that cannot move.
#
# Two costs to contain:
#   * `ros2 control list_controllers` needs a full Pixi activation, far too slow
#     for the launcher's 1s poll, so the answer is cached briefly.
#   * it blocks waiting for /controller_manager when the manager is down, so the
#     call is bounded (macOS ships no coreutils `timeout`).

set -uo pipefail

MIN_ACTIVE="${1:-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TTL="${LUCY_CONTROLLERS_CACHE_TTL:-8}"
CALL_TIMEOUT="${LUCY_CONTROLLERS_TIMEOUT:-12}"
CACHE="${TMPDIR:-/tmp}/lucy_controllers_active.$(id -u).cache"

now=$(date +%s)
if [[ -f "${CACHE}" ]]; then
  read -r stamp cached < "${CACHE}" 2>/dev/null || { stamp=0; cached=1; }
  if [[ "${stamp}" =~ ^[0-9]+$ ]] && (( now - stamp < TTL )); then
    exit "${cached:-1}"
  fi
fi

export PATH="${HOME}/.pixi/bin:${PATH}"
command -v pixi >/dev/null 2>&1 || exit 1

out="${CACHE}.out"
(
  cd "${ROOT}" || exit 1
  pixi run -- bash -c 'source scripts/dds_env.sh 2>/dev/null; ros2 control list_controllers' \
    > "${out}" 2>&1
) &
probe_pid=$!

waited=0
while kill -0 "${probe_pid}" 2>/dev/null && (( waited < CALL_TIMEOUT * 10 )); do
  sleep 0.1
  waited=$((waited + 1))
done
if kill -0 "${probe_pid}" 2>/dev/null; then
  kill -9 "${probe_pid}" 2>/dev/null
  wait "${probe_pid}" 2>/dev/null
fi
wait "${probe_pid}" 2>/dev/null

# grep -c prints a count and still exits 1 on zero matches, so take the count
# and normalise rather than chaining a fallback that would append a second line.
active=$(grep -cE '[[:space:]]active[[:space:]]*$' "${out}" 2>/dev/null)
[[ "${active}" =~ ^[0-9]+$ ]] || active=0
rm -f "${out}"

if (( active >= MIN_ACTIVE )); then result=0; else result=1; fi
printf '%s %s\n' "${now}" "${result}" > "${CACHE}" 2>/dev/null || true
exit "${result}"
