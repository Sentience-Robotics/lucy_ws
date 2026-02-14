#!/usr/bin/env bash
# Run Lucy ROS 2 Humble environment in Docker (Ubuntu 22.04): thais_urdf + lucy_ros2_control with Gazebo, RViz and rosbridge.
#
# Prerequisite: run install.sh once to clone src/ and build the image (or build manually).
#
# Usage:
#   ./launch_lucy.sh              # interactive shell with X11 (RViz2/Gazebo)
#   ./launch_lucy.sh --headless   # shell without GUI
#   ./launch_lucy.sh --install   # build workspace only and exit (no shell)
#   ./launch_lucy.sh <command>   # run one command in the container
#
# Control panel (outside Docker): connect to rosbridge at ws://localhost:9090
# For GUI: xhost +local:docker before first run.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="lucy_ros2_control:humble"
WORKSPACE="/workspace"
URDF_PATH="$WORKSPACE/src/thais_urdf/inmoov/urdf/inmoov.urdf.xacro"
BASE_PATH="$WORKSPACE/src/thais_urdf/inmoov"

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
      echo "GUI: DISPLAY=$GUI_DISPLAY (see docker/DISPLAY_FIX.md if connection fails)"
    fi
  else
    echo "GUI: DISPLAY not set; launch will run Gazebo headless (RViz disabled)."
  fi
fi

# Build image if missing
if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building Docker image $IMAGE_NAME (one-time)..."
  docker build -f "$SCRIPT_DIR/Dockerfile.humble" -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

SETUP="source /opt/ros/humble/setup.bash"
# Build all workspace packages and source overlay (install step)
BUILD_AND_SOURCE="cd $WORKSPACE && colcon build && source install/setup.bash"
# Real robot + RViz + rosbridge (control panel at ws://localhost:9090)
LAUNCH_RVIZ_CONTROL_BRIDGE="ros2 launch thais_urdf rviz.launch.py"
# Real robot, ros2_control only (no RViz, no rosbridge)
LAUNCH_CONTROL="ros2 launch lucy_ros2_control control.launch.py"
# Gazebo sim + RViz + rosbridge (control panel; sim must be running for motion)
LAUNCH_GAZEBO_RVIZ_BRIDGE="ros2 launch thais_urdf gazebo.launch.py"

# Expose rosbridge so control panel on host can connect
PORT_ROSBRIDGE=9090
DOCKER_PORT_ARGS=(-p "${PORT_ROSBRIDGE}:9090")

# --install: rosdep install then build workspace and exit (no interactive shell)
if [ "${1:-}" = "--install" ]; then
  echo "Install: rosdep install, then building workspace and exiting..."
  docker run -it --rm \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "$IMAGE_NAME" -c "${SETUP} && cd $WORKSPACE && rosdep install --from-paths src --ignore-src -r -y && colcon build"
  echo "Done. Run ./launch_lucy.sh to start a shell."
  exit 0
fi

if [ $# -eq 0 ]; then
  echo "Starting Humble shell (ROS + workspace built and sourced). Workspace: $WORKSPACE"
  echo "  Real + RViz + rosbridge: $LAUNCH_RVIZ_CONTROL_BRIDGE"
  echo "  Real, ros2_control only: $LAUNCH_CONTROL"
  echo "  Gazebo sim + RViz + rosbridge: $LAUNCH_GAZEBO_RVIZ_BRIDGE"
  echo "  Control panel URL (outside Docker): ws://localhost:${PORT_ROSBRIDGE}"
  docker run -it --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "$IMAGE_NAME" -c "${SETUP} && ${BUILD_AND_SOURCE} && exec /bin/bash"
else
  docker run -it --rm \
    "${DOCKER_PORT_ARGS[@]}" \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "${X11_ARGS[@]}" \
    "$IMAGE_NAME" -c "${SETUP} && ${BUILD_AND_SOURCE} && $*"
fi
