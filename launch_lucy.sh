#!/usr/bin/env bash
# Start the Lucy stack (ROS 2 Jazzy + control panel) inside Docker.
#
# Prerequisite: ./install.sh — clones src/, builds the Docker image, builds the workspace.
#
# Usage:
#   ./launch_lucy.sh                start control panel + `ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true`
#   ./launch_lucy.sh --headless     same but without GUI / X11 (Gazebo runs headless, RViz disabled)
#   ./launch_lucy.sh <command>      run a single command in the container (no control panel, no auto-launch)
#
# Dev mode (DEV=true in env or .env): drop into an interactive Jazzy shell with the control
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

# A free-host-port search so a port already taken (e.g. macOS AirPlay on 5000)
# doesn't abort the launch — we publish on the next available one and the printed
# URLs reflect it. Only the host side moves; the container keeps its fixed port.
host_port_in_use() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}

resolve_host_port() {  # $1 = label, $2 = desired port -> echoes a free port
  local p="$2" limit=$(( $2 + 50 ))
  while [ "$p" -le "$limit" ]; do
    if ! host_port_in_use "$p"; then
      [ "$p" != "$2" ] && echo "Port $2 ($1) in use; using $p instead." >&2
      echo "$p"; return 0
    fi
    p=$((p + 1))
  done
  echo "$2"  # nothing free in range; let docker surface the real error
}

IMAGE_NAME="lucy_ros2:jazzy"
DOCKERFILE_PATH="$SCRIPT_DIR/docker/Dockerfile.jazzy"
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
GUI_PORT_ARGS=()
ARCH="$(uname -m)"
# LUCY_FORCE_VNC selects the in-container VNC desktop:
#   unset  -> auto: VNC on arm64 (no working native GL), native X11 on amd64
#   1/yes  -> force VNC on any arch (also set it for ./install.sh so the image
#             is built with the VNC tooling)
#   0/no   -> force VNC off even on arm64 (falls back to native X11 / headless)
USE_VNC=0
case "$ARCH" in arm64|aarch64) USE_VNC=1 ;; esac
case "$(echo "${LUCY_FORCE_VNC:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) USE_VNC=1 ;;
  0|false|no) USE_VNC=0 ;;
esac
if [ "${1:-}" = "--headless" ]; then
  shift
  echo "Headless: no X11 (Gazebo runs headless; RViz is disabled by the launch)."
elif [ "$USE_VNC" = 1 ]; then
  # VNC desktop: native X11/GLX is unavailable or unreliable for GL apps (RViz,
  # Gazebo). Offer an opt-in virtual desktop via noVNC/VNC from the launcher. The
  # display is not started automatically — enable it in the launcher.
  GUI_VNC_PORT="$(resolve_host_port VNC "${LUCY_GUI_VNC_PORT:-5901}")"
  GUI_NOVNC_PORT="$(resolve_host_port noVNC "${LUCY_GUI_NOVNC_PORT:-6080}")"
  GUI_VNC_PASSWORD="${LUCY_GUI_VNC_PASSWORD:-lucy}"
  X11_ARGS=(
    -e LUCY_GUI_VNC_AVAILABLE=1
    -e LUCY_GUI_VNC_PASSWORD="$GUI_VNC_PASSWORD"
    -e LUCY_ORIGINAL_DISPLAY="${DISPLAY:-}"
    -e LIBGL_ALWAYS_SOFTWARE=1
    -e GALLIUM_DRIVER=llvmpipe
    -e LUCY_GUI_NOVNC_PUBLISHED_PORT="$GUI_NOVNC_PORT"
    -e LUCY_GUI_VNC_PUBLISHED_PORT="$GUI_VNC_PORT"
  )
  GUI_PORT_ARGS=(
    -p "${GUI_VNC_PORT}:5901"
    -p "${GUI_NOVNC_PORT}:6080"
  )
  echo "GUI: in-container virtual desktop available (enable noVNC or VNC in the launcher)."
  echo "       Browser (noVNC):  http://localhost:${GUI_NOVNC_PORT}/vnc.html  (no password)"
  echo "       VNC Viewer:       localhost:${GUI_VNC_PORT}  (password: ${GUI_VNC_PASSWORD})"
else
  # AMD64: native X11 forwarding, no VNC.
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

# Scheme the LCP serves on: https when VITE_HTTPS=true, else http.
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

PORT_ROSBRIDGE="$(resolve_host_port rosbridge "${PORT_ROSBRIDGE:-9090}")"
if [[ -z "${PORT_CONTROL_PANEL_CONTAINER:-}" ]]; then
  if v="$(vite_listen_port_from_envfile)"; then
    PORT_CONTROL_PANEL_CONTAINER="$v"
  else
    PORT_CONTROL_PANEL_CONTAINER=5000
  fi
fi
PORT_CONTROL_PANEL="$(resolve_host_port 'control panel' "${PORT_CONTROL_PANEL:-$PORT_CONTROL_PANEL_CONTAINER}")"
LCP_SCHEME="${LUCY_LCP_SCHEME:-$(vite_scheme_from_envfile)}"

DOCKER_PORT_ARGS=(
  -p "${PORT_ROSBRIDGE}:9090"
  -p "${PORT_CONTROL_PANEL}:${PORT_CONTROL_PANEL_CONTAINER}"
)

DOCKER_ENV_ARGS=(
  -e LUCY_LCP_PUBLISHED_HOST_PORT="$PORT_CONTROL_PANEL"
  -e LUCY_LCP_CONTAINER_PORT="$PORT_CONTROL_PANEL_CONTAINER"
  -e LUCY_LCP_SCHEME="$LCP_SCHEME"
)

# ----------------------------------------------------------------------------
# Container scripts
# ----------------------------------------------------------------------------

SETUP="source /opt/ros/jazzy/setup.bash"
SOURCE_WORKSPACE="cd $WORKSPACE && source install/setup.bash"
LAUNCH_GAZEBO_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true"
LAUNCH_RVIZ_BRIDGE_CP="ros2 launch lucy_bringup lucy.launch.py rviz:=true"

# Preamble run inside the container: source ROS + overlay.
read -r -d '' CONTAINER_PREAMBLE <<'EOS' || true
set -e;
source /opt/ros/jazzy/setup.bash
[ -f /opt/gz_ros2_control_ws/install/setup.bash ] && source /opt/gz_ros2_control_ws/install/setup.bash
cd /workspace
if [[ ! -f install/setup.bash ]]; then
  echo "Workspace not built. Run Install/Update via Lucy.py" >&2
  exit 1
fi
source install/setup.bash
EOS

# In DEV mode, attach to a tmux session. Exiting the last tmux window will exit the container.
read -r -d '' TMUX_SCRIPT <<'EOS' || true
if [ -z "$TMUX" ]; then
  # Start tmux server and create session if it doesn't exist
  tmux start-server
  if ! tmux has-session -t lucy_ws 2>/dev/null; then
    tmux new-session -d -s lucy_ws -n 'Lucy Workspace'
  fi

  # Send the command
  tmux send-keys -t lucy_ws "launcher" C-m

  # Attach to session.
  # When the last window is closed, the server exits, the script ends, and the container stops.
  tmux attach-session -t lucy_ws
else
  # Already inside tmux, do nothing special.
  bash -i
fi
EOS

INTERACTIVE_CONTAINER_SCRIPT="${CONTAINER_PREAMBLE}
${TMUX_SCRIPT}
"

NORMAL_CONTAINER_SCRIPT="${CONTAINER_PREAMBLE}
${LAUNCH_GAZEBO_RVIZ_BRIDGE_CP}
"

# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------

if [ $# -eq 0 ]; then
  CONTAINER_SCRIPT="$INTERACTIVE_CONTAINER_SCRIPT"
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    --name lucy_dev \
    "${DOCKER_PORT_ARGS[@]}" \
    "${GUI_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "${DOCKER_ENV_ARGS[@]}" \
    "$IMAGE_NAME" bash -c "$CONTAINER_SCRIPT"
else
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    --name lucy_dev \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "$IMAGE_NAME" bash -c "${SETUP} && ${SOURCE_WORKSPACE} && $*"
fi
