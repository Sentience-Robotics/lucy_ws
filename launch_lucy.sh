#!/usr/bin/env bash
# Start the Lucy stack (ROS 2 Jazzy + Control Center launcher) via Pixi.
#
# Prerequisite: ./install.sh
#
# Usage:
#   ./launch_lucy.sh                tmux + Control Center launcher (default)
#   ./launch_lucy.sh --headless <cmd>  run a single command, e.g. ros2 doctor --report
#
# Dev mode (DEV=true): interactive pixi shell with ros2 launch hints.
#
# Sets LUCY_LCP_* env vars for control panel URLs in the launcher.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

host_port_in_use() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}

resolve_host_port() {
  local label="$1"
  local p="$2"
  local limit=$((p + 50))
  while [ "$p" -le "$limit" ]; do
    if ! host_port_in_use "$p"; then
      if [ "$p" != "$2" ]; then
        echo "Port $2 ($label) in use; using $p instead." >&2
      fi
      echo "$p"
      return 0
    fi
    p=$((p + 1))
  done
  echo "$2"
}

vite_listen_port_from_envfile() {
  local f="$SCRIPT_DIR/src/lucy_control_panel/.env"
  local raw val
  [[ -f "$f" ]] || return 1
  raw=$(grep -E '^[[:space:]]*VITE_PORT[[:space:]]*=' "$f" | tail -1 2>/dev/null || true)
  [[ -n "$raw" ]] || return 1
  val="${raw#*=}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  val="${val//\"/}"
  val="${val//\'/}"
  [[ "$val" =~ ^[0-9]+$ ]] || return 1
  echo "$val"
}

vite_scheme_from_envfile() {
  local f="$SCRIPT_DIR/src/lucy_control_panel/.env"
  local raw val
  [[ -f "$f" ]] || { echo "http"; return; }
  raw=$(grep -E '^[[:space:]]*VITE_HTTPS[[:space:]]*=' "$f" | tail -1 2>/dev/null || true)
  val="${raw#*=}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  val="${val//\"/}"
  val="${val//\'/}"
  if [[ "$(echo "$val" | tr '[:upper:]' '[:lower:]')" == "true" ]]; then
    echo "https"
  else
    echo "http"
  fi
}

check_cmd pixi

if [[ ! -f "$SCRIPT_DIR/install/setup.bash" ]]; then
  echo "Workspace not built. Run ./install.sh or Install in Lucy.py" >&2
  exit 1
fi

PORT_CONTROL_PANEL_CONTAINER="${PORT_CONTROL_PANEL_CONTAINER:-}"
if [[ -z "$PORT_CONTROL_PANEL_CONTAINER" ]]; then
  if v="$(vite_listen_port_from_envfile)"; then
    PORT_CONTROL_PANEL_CONTAINER="$v"
  else
    PORT_CONTROL_PANEL_CONTAINER=5000
  fi
fi
PORT_CONTROL_PANEL="$(resolve_host_port 'control panel' "${PORT_CONTROL_PANEL:-$PORT_CONTROL_PANEL_CONTAINER}")"
LCP_SCHEME="${LUCY_LCP_SCHEME:-$(vite_scheme_from_envfile)}"

export LUCY_LCP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL"
export LUCY_LCP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER"
export LUCY_LCP_SCHEME="$LCP_SCHEME"

echo "Control panel: ${LCP_SCHEME}://localhost:${PORT_CONTROL_PANEL}"

case "${1:-}" in
  --headless)
    shift
    if [ $# -eq 0 ]; then
      set -- ros2 doctor --report
    fi
    exec pixi run -- "$@"
    ;;
esac

if [ "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
  echo "Dev mode — pixi shell (workspace overlay active)."
  echo "  ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true"
  echo "  ros2 launch lucy_bringup lucy.launch.py real:=true"
  exec pixi shell
fi

# Git Bash / MSYS on Windows: no tmux — run the Control Center launcher directly.
case "$(uname -s)" in
  Linux|Darwin)
    if command -v tmux >/dev/null 2>&1; then
      exec pixi run -- bash -c '
        set -e
        tmux start-server
        if ! tmux has-session -t lucy_ws 2>/dev/null; then
          tmux new-session -d -s lucy_ws -n Lucy "python3 launcher.py"
        else
          tmux send-keys -t lucy_ws:Lucy C-c 2>/dev/null || true
          tmux send-keys -t lucy_ws:Lucy "python3 launcher.py" C-m
        fi
        tmux attach-session -t lucy_ws
      '
    fi
    ;;
esac

exec pixi run -- python launcher.py
