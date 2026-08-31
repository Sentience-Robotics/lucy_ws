#!/usr/bin/env bash
# Canonical Jetson detection for Lucy host GL / Gazebo setup.
# Keep in sync with lucy_control_supervisor.jetson_platform (Python).

lucy_is_jetson() {
  case "${LUCY_GPU_MODE:-}" in
    jetson|tegra) return 0 ;;
    0|false|no|off|disable) return 1 ;;
  esac
  [[ -f /etc/nv_tegra_release ]] && return 0
  if [[ -r /proc/device-tree/model ]]; then
    local model
    model=$(tr -d '\0' </proc/device-tree/model | tr '[:upper:]' '[:lower:]')
    [[ "$model" == *jetson* || "$model" == *tegra* ]]
    return $?
  fi
  return 1
}

lucy_headless_runtime_dir() {
  printf '%s\n' "${LUCY_HEADLESS_RUNTIME_DIR:-/tmp/runtime-root}"
}

lucy_ensure_headless_runtime_dir() {
  local dir
  dir=$(lucy_headless_runtime_dir)
  mkdir -p "$dir"
  chmod 0700 "$dir"
  export XDG_RUNTIME_DIR="$dir"
}
