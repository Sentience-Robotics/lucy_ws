#!/usr/bin/env bash
# Run Lucy ROS 2 Humble in Docker: ``lucy_bringup/lucy.launch.py`` (args: real, rviz, gazebo) + workspace overlay.
#
# Prerequisite: ./install.sh (or ./install.sh --build-only) — clones src/, Docker image, colcon build, yarn for control panel.
#
# Usage:
#   ./launch_lucy.sh                # interactive shell; Vite control panel in background (see printed ros2 launch hints)
#   ./launch_lucy.sh --headless     # same without GUI forwarding
#   ./launch_lucy.sh <command>      # run one command in the container (no control panel)
#
# Docker platform matches the last ./install.sh run (see .lucy-docker-platform; override with LUCY_DOCKER_PLATFORM).
#
# Ports mapped to host: rosbridge 9090, control panel PORT_CONTROL_PANEL (match lucy_control_panel VITE_PORT / .env).
# Vite proxies /rosbridge -> ws://127.0.0.1:9090 inside the container.
# Dockerfile rebuild when Dockerfile.humble changes is handled via LABEL lucy.dockerfile.sha256 (see docker/ensure_image.sh).
# For GUI: xhost +local:docker before first run.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_NAME="lucy_ros2_control:humble"
DOCKERFILE_PATH="$SCRIPT_DIR/Dockerfile.humble"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/docker/ensure_image.sh"

ensure_docker_image() {
  ensure_lucy_docker_image "$SCRIPT_DIR" "$IMAGE_NAME" "$DOCKERFILE_PATH"
}
WORKSPACE="/workspace"

# X11 by default; use --headless to disable. Set DOCKER_GUI_DISPLAY if host DISPLAY doesn't work (e.g. Docker Desktop).
# See docker/DISPLAY_FIX.md for full instructions.
X11_ARGS=()
if [ "${1:-}" = "--headless" ]; then
  shift
  echo "Headless: no X11 (Gazebo/RViz will run headless or fail if launched)."
else
  GUI_DISPLAY="${DOCKER_GUI_DISPLAY:-$DISPLAY}"
  if [ -n "$GUI_DISPLAY" ]; then
    if command -v xhost &>/dev/null; then
      xhost +local:docker 2>/dev/null || true
    fi
    if [ -n "${DOCKER_GUI_USE_HOST_NETWORK:-}" ]; then
      X11_ARGS=(-e "DISPLAY=:0" --network=host)
      echo "GUI: DISPLAY=:0 (host network). See docker/DISPLAY_FIX.md if connection fails."
    else
      X11_ARGS=(-e DISPLAY="$GUI_DISPLAY" -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
      echo "GUI: DISPLAY=$GUI_DISPLAY"
    fi
  else
    echo "GUI: DISPLAY not set; launch will run Gazebo headless (RViz disabled)."
  fi
fi

ensure_docker_image
docker_run_platform_flags "$SCRIPT_DIR"
docker_run_it_flags

# Vite reads lucy_control_panel/.env (VITE_PORT); Docker must publish that container port or the host URL lies.
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

SETUP="source /opt/ros/humble/setup.bash"
SOURCE_WORKSPACE="cd $WORKSPACE && source install/setup.bash"
LAUNCH_GAZEBO_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py gazebo:=true real:=false"
LAUNCH_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py real:=false rviz:=true"

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

# Bash fragment run inside the container for interactive sessions (source overlay, background Vite, login shell).
# Uses bash -i (not exec) so EXIT trap runs when the user exits and stops Vite.
read -r -d '' INTERACTIVE_CONTAINER_SCRIPT <<'EOS' || true
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
    echo "Control panel: yarn/npm missing in image; rebuild Docker image."
  fi
  cd /workspace
  if [[ -n "${CP_PID:-}" ]]; then
    disown "$CP_PID" 2>/dev/null || true
    echo "Control panel (Vite) in background (PID $CP_PID). Host UI: http://localhost:${LUCY_CP_PUBLISHED_HOST_PORT}/ — log: tail -f /tmp/lucy-control-panel-vite.log"
    echo "  (Port follows lucy_control_panel/.env VITE_PORT if set.)"
  fi
fi

bash -i
EOS

if [ $# -eq 0 ]; then
  echo "Starting Humble shell (ROS workspace sourced; build with ./install.sh). Workspace: $WORKSPACE"
  echo "  Control panel auto-starts in background — http://localhost:${PORT_CONTROL_PANEL}/ — log: tail -f /tmp/lucy-control-panel-vite.log"
  echo "  Rosbridge on host: port ${PORT_ROSBRIDGE}"
  echo ""
  echo "  Typical stacks (run inside this shell after rosbridge is up):"
  echo "    • Gazebo + RViz + Control Panel  →  $LAUNCH_GAZEBO_RVIZ_BRIDGE_CP"
  echo "    • RViz + Control Panel           →  $LAUNCH_RVIZ_BRIDGE_CP"
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    -e LUCY_CP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL" \
    -e LUCY_CP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER" \
    "$IMAGE_NAME" -c "$INTERACTIVE_CONTAINER_SCRIPT"
else
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "$IMAGE_NAME" -c "${SETUP} && ${SOURCE_WORKSPACE} && $*"
fi
