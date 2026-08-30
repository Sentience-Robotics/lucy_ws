#!/usr/bin/env bash
# Interactive Pixi shell with RoboStack + colcon overlay (for ros2 CLI debugging).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
echo "Lucy dev shell — RoboStack + install/ overlay active."
echo ""
echo "  ros2 topic list          ros2 service list"
echo "  ros2 launch lucy_bringup lucy.launch.py rviz:=true"
echo ""
echo "  Or use pixi component tasks from another terminal:"
echo "    pixi run core | sim-headless | sim-rviz | rviz | control-panel | rqt | lucy-cli"
echo ""
echo "  Robot package (default inmoov_urdf):"
echo "    LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-headless"
echo ""
exec pixi shell
