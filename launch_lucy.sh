#!/usr/bin/env bash
# Start the Lucy stack (ROS 2 Humble + control panel) inside Docker.
#
# Prerequisite: ./install.sh — clones src/, builds the Docker image, builds the workspace.
#
# Usage:
#   ./launch_lucy.sh                start control panel + `ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true`
#   ./launch_lucy.sh --headless     same but without GUI / X11 (Gazebo runs headless, RViz disabled)
#   ./launch_lucy.sh <command>      run a single command in the container (no control panel, no auto-launch)
#
# Dev mode (DEV=true in env or .env): drop into an interactive Humble shell with the control
# panel running in background; you launch the ROS stack yourself (handy commands are printed).
#
# Ports published on the host: rosbridge 9090, control panel PORT_CONTROL_PANEL (defaults to
# VITE_PORT from src/lucy_control_panel/.env, else 5000). Vite proxies /rosbridge to the bridge.
#
# Docker platform follows the last ./install.sh run (.lucy-docker-platform; override with LUCY_DOCKER_PLATFORM).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

case "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) DEV_MODE=1 ;;
  *) DEV_MODE=0 ;;
esac

IMAGE_NAME="lucy_ros2:humble"
DOCKERFILE_PATH="$SCRIPT_DIR/Dockerfile.humble"
WORKSPACE="/workspace"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/docker/ensure_image.sh"

ensure_docker_image() {
  ensure_lucy_docker_image "$SCRIPT_DIR" "$IMAGE_NAME" "$DOCKERFILE_PATH"
}

# ----------------------------------------------------------------------------
# GUI / X11 forwarding
# ----------------------------------------------------------------------------
# GUI on by default. `--headless` disables it. Override the display with
# DOCKER_GUI_DISPLAY (e.g. Docker Desktop) or use DOCKER_GUI_USE_HOST_NETWORK=1
# to share the host network namespace (DISPLAY=:0 inside the container).

X11_ARGS=()
if [ "${1:-}" = "--headless" ]; then
  shift
  echo "Headless: no X11 (Gazebo runs headless; RViz is disabled by the launch)."
else
  GUI_DISPLAY="${DOCKER_GUI_DISPLAY:-$DISPLAY}"
  if [ -n "$GUI_DISPLAY" ]; then
    if command -v xhost &>/dev/null; then
      xhost +local:docker 2>/dev/null || true
    fi
    if [ -n "${DOCKER_GUI_USE_HOST_NETWORK:-}" ]; then
      X11_ARGS=(-e "DISPLAY=:0" --network=host)
      echo "GUI: DISPLAY=:0 (host network)."
    else
      X11_ARGS=(-e DISPLAY="$GUI_DISPLAY" -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
      echo "GUI: DISPLAY=$GUI_DISPLAY"
    fi
  else
    echo "GUI: DISPLAY not set; Gazebo will run headless (RViz disabled)."
  fi
fi

ensure_docker_image
docker_run_platform_flags "$SCRIPT_DIR"
docker_run_it_flags

# ----------------------------------------------------------------------------
# Port mapping (control panel + rosbridge)
# ----------------------------------------------------------------------------

# Vite reads VITE_PORT from src/lucy_control_panel/.env. We must publish that
# exact container port, otherwise the printed host URL silently lies.
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

PORT_ROSBRIDGE=9090
if [[ -z "${PORT_CONTROL_PANEL_CONTAINER:-}" ]]; then
  if v="$(vite_listen_port_from_envfile)"; then
    PORT_CONTROL_PANEL_CONTAINER="$v"
  else
    PORT_CONTROL_PANEL_CONTAINER=5000
  fi
fi
PORT_CONTROL_PANEL="${PORT_CONTROL_PANEL:-$PORT_CONTROL_PANEL_CONTAINER}"

DOCKER_PORT_ARGS=(
  -p "${PORT_ROSBRIDGE}:9090"
  -p "${PORT_CONTROL_PANEL}:${PORT_CONTROL_PANEL_CONTAINER}"
)

# ----------------------------------------------------------------------------
# Container scripts
# ----------------------------------------------------------------------------

SETUP="source /opt/ros/humble/setup.bash"
SOURCE_WORKSPACE="cd $WORKSPACE && source install/setup.bash"
LAUNCH_GAZEBO_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true"
LAUNCH_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py rviz:=true"

# Preamble run inside the container: source ROS + overlay, then start the Vite
# control panel in the background. An EXIT/INT/TERM trap stops Vite when the
# foreground command (bash -i in dev mode, or `ros2 launch` in normal mode) ends.
read -r -d '' CONTAINER_PREAMBLE <<'EOS' || true
set -e
source /opt/ros/humble/setup.bash
cd /workspace
if [[ ! -f install/setup.bash ]]; then
  echo "Workspace not built. Run ./install.sh (or ./install.sh --build-only) on the host first." >&2
  exit 1
fi
source install/setup.bash

cleanup_lucy_bg() {
  [[ -n "${CP_PID:-}" ]] && kill "$CP_PID" 2>/dev/null || true
}
trap cleanup_lucy_bg EXIT INT TERM

CP_PID=
if [[ -f src/lucy_control_panel/package.json ]]; then
  cd src/lucy_control_panel
  if command -v yarn >/dev/null 2>&1; then
    yarn dev > /tmp/lucy-control-panel-vite.log 2>&1 &
    CP_PID=$!
  elif command -v npm >/dev/null 2>&1; then
    npm run dev > /tmp/lucy-control-panel-vite.log 2>&1 &
    CP_PID=$!
  else
    echo "Control panel: yarn/npm missing in image; rebuild Docker image." >&2
  fi
  cd /workspace
  if [[ -n "${CP_PID:-}" ]]; then
    disown "$CP_PID" 2>/dev/null || true
    echo "Control panel (Vite) in background (PID $CP_PID). Host UI: http://localhost:${LUCY_CP_PUBLISHED_HOST_PORT}/ — log: tail -f /tmp/lucy-control-panel-vite.log"
  fi
fi
EOS

INTERACTIVE_CONTAINER_SCRIPT="${CONTAINER_PREAMBLE}
bash -i
"

NORMAL_CONTAINER_SCRIPT="${CONTAINER_PREAMBLE}
${LAUNCH_GAZEBO_RVIZ_BRIDGE_CP}
"

# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------

if [ $# -eq 0 ]; then
  if [ "$DEV_MODE" = 1 ]; then
    echo "DEV mode: interactive Humble shell (workspace already built by ./install.sh). Mount: $WORKSPACE"
    echo "  Control panel: http://localhost:${PORT_CONTROL_PANEL}/ — log: tail -f /tmp/lucy-control-panel-vite.log"
    echo "  Rosbridge on host: port ${PORT_ROSBRIDGE}"
    echo ""
    echo "  Typical launches:"
    echo "    • Gazebo + RViz + Control Panel  ->  $LAUNCH_GAZEBO_RVIZ_BRIDGE_CP"
    echo "    • RViz + Control Panel           ->  $LAUNCH_RVIZ_BRIDGE_CP"
    CONTAINER_SCRIPT="$INTERACTIVE_CONTAINER_SCRIPT"
  else
    echo "Starting Lucy stack: Control Panel + RViz + Gazebo (set DEV=true for an interactive shell)."
    echo "  Control panel: http://localhost:${PORT_CONTROL_PANEL}/ — log: tail -f /tmp/lucy-control-panel-vite.log"
    echo "  Rosbridge on host: port ${PORT_ROSBRIDGE}"
    echo "  Launching: $LAUNCH_GAZEBO_RVIZ_BRIDGE_CP"
    CONTAINER_SCRIPT="$NORMAL_CONTAINER_SCRIPT"
  fi
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    -e LUCY_CP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL" \
    -e LUCY_CP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER" \
    "$IMAGE_NAME" -c "$CONTAINER_SCRIPT"
else
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "$IMAGE_NAME" -c "${SETUP} && ${SOURCE_WORKSPACE} && $*"
fi
