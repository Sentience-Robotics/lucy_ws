#!/usr/bin/env bash
# Bash helpers for Jetson detection. Logic lives in launcher/platform.py.

_LUCY_WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_lucy_jetson_python() {
  if [[ -x "${_LUCY_WS_ROOT}/.pixi/envs/default/bin/python" ]]; then
    printf '%s\n' "${_LUCY_WS_ROOT}/.pixi/envs/default/bin/python"
  elif command -v python &>/dev/null; then
    command -v python
  else
    command -v python3
  fi
}

_lucy_jetson_py() {
  local py
  py="$(_lucy_jetson_python)"
  PYTHONPATH="${_LUCY_WS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" "${py}" "$@"
}

lucy_is_jetson() {
  _lucy_jetson_py -c "from launcher.platform import is_jetson; import sys; sys.exit(0 if is_jetson() else 1)"
}

lucy_headless_runtime_dir() {
  _lucy_jetson_py -c "from launcher.platform import headless_runtime_dir; print(headless_runtime_dir(), end='')"
}

lucy_ensure_headless_runtime_dir() {
  local dir
  dir="$(_lucy_jetson_py -c "from launcher.platform import ensure_headless_runtime_dir; print(ensure_headless_runtime_dir(), end='')")"
  export XDG_RUNTIME_DIR="$dir"
}
