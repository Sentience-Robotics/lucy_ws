#!/usr/bin/env bash
# Run a GUI ROS tool inside Pixi with host GL env (Jetson / NixOS).
#
# Usage:
#   bash scripts/pixi_gui_launch.sh rqt
#   bash scripts/pixi_gui_launch.sh ros2 run lucy_cli tui

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/nix_gl_env.sh
source "${ROOT}/scripts/nix_gl_env.sh"
cd "${ROOT}"
exec "$@"
