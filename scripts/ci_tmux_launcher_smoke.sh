#!/usr/bin/env bash
# CI smoke: tmux + pixi-wrapped core (headless sim) and control panel.
# Exercises the same tmux/pixi paths as launcher.py apply_changes without the TUI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v tmux >/dev/null 2>&1; then
  echo "ci_tmux_launcher_smoke: tmux not found" >&2
  exit 1
fi

if [[ ! -f "${ROOT}/install/setup.bash" ]]; then
  echo "ci_tmux_launcher_smoke: workspace not built" >&2
  exit 1
fi

printf 'DEV=true\n' > .env

export LUCY_WS_ROOT="$ROOT"

tmux start-server
tmux kill-session -t lucy_ws 2>/dev/null || true
tmux new-session -d -s lucy_ws -n Lucy 'sleep 300'

pixi run -- python3 <<'PY'
import os

os.chdir(os.environ["LUCY_WS_ROOT"])
from launcher import (
    load_workspace_env,
    _tmux_new_pixi_window,
    run_shell_command,
)

load_workspace_env()

core_cmd = (
    "ros2 launch lucy_bringup lucy.launch.py "
    "robot_package:=inmoov_urdf gazebo:=true headless:=true"
)
run_shell_command(_tmux_new_pixi_window("core", core_cmd, remain_on_exit=True))
run_shell_command(
    _tmux_new_pixi_window("control_panel", "pixi run panel-dev", remain_on_exit=True)
)
PY

wait_for() {
  local pattern="$1"
  local label="$2"
  local timeout="${3:-180}"
  local elapsed=0
  while ! pgrep -f "$pattern" >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "ci_tmux_launcher_smoke: timeout waiting for ${label}" >&2
      tmux list-windows -t lucy_ws 2>/dev/null || true
      return 1
    fi
  done
  echo "ci_tmux_launcher_smoke: ${label} up (${elapsed}s)"
}

wait_for '[r]osbridge_websocket' 'rosbridge' 180
wait_for '[v]ite' 'control panel (vite)' 180

tmux kill-session -t lucy_ws 2>/dev/null || true
echo "ci_tmux_launcher_smoke: OK"
