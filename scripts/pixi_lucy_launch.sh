#!/usr/bin/env bash
# Run lucy_bringup inside Pixi with NixOS GL env (scripts/nix_gl_env.sh).
#
# Usage:
#   pixi run core
#   pixi run sim-headless
#   LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-rviz
#
# Extra ros2 launch args are forwarded:
#   bash scripts/pixi_lucy_launch.sh gazebo:=true real:=false

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/nix_gl_env.sh
source "${ROOT}/scripts/nix_gl_env.sh"
ROBOT="${LUCY_ROBOT_PACKAGE:-inmoov_urdf}"
cd "${ROOT}"
exec ros2 launch lucy_bringup lucy.launch.py "robot_package:=${ROBOT}" "$@"
