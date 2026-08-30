#!/usr/bin/env bash
# CI-friendly colcon test: stable skips, optional thais_urdf, pytest plugin guard.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

skip=(lucy_cli lucy_config_pipeline lucy_control_supervisor camera_ros)
if [ -d "src/thais_urdf" ]; then
  skip+=(thais_urdf)
fi

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

args=(test --return-code-on-test-failure --packages-skip "${skip[@]}")
for opt in "$@"; do
  args+=("$opt")
done

exec colcon "${args[@]}"
