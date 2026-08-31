#!/usr/bin/env bash
# Host GL env for Pixi/RoboStack (Gazebo, RViz, rqt) on NixOS and Jetson.
#
# Pixi activation puts conda Mesa/GLVND first on LD_LIBRARY_PATH; on NixOS +
# Wayland or Jetson Tegra that breaks gz sim (ogre2 plugin load failures, EGL
# segfaults, hung spawners). This script runs *inside* pixi run and:
#   1. Prepends host GL libs (NixOS nixGL / opengl-driver, or Jetson tegra/nvidia)
#   2. Sets EGL vendor + GZ_IP for OGRE / Gazebo transport
#
# Usage (via scripts/pixi_lucy_launch.sh, scripts/pixi_gui_launch.sh, launcher):
#   pixi run sim
#
# Do not set LUCY_NIX_GL=0 on NixOS or Jetson — EGL vars alone are not enough.
# Override wrapper (NixOS AMD/NVIDIA): LUCY_NIX_GL_WRAPPER=nixGLIntel
# Force Jetson mode elsewhere: LUCY_GPU_MODE=jetson

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/detect_jetson.sh
source "${ROOT}/scripts/detect_jetson.sh"
# shellcheck source=scripts/gz_rendering_env.sh
source "${ROOT}/scripts/gz_rendering_env.sh"

_lucy_on_nixos() {
  [[ -d /run/opengl-driver ]] || [[ -n "${LUCY_NIXOS:-}" ]]
}

_lucy_prepend_jetson_gl() {
  case "${LUCY_NIX_GL:-auto}" in
    0|false|no|off|disable)
      if lucy_is_jetson; then
        echo "nix_gl_env.sh: LUCY_NIX_GL=0 — Jetson GL libs not prepended; Gazebo rendering may fail." >&2
      fi
      return 0
      ;;
  esac

  local jetson_ld="" candidate
  for candidate in \
    /usr/lib/aarch64-linux-gnu/nvidia:/usr/lib/aarch64-linux-gnu/tegra \
    /usr/lib/aarch64-linux-gnu/tegra:/usr/lib/aarch64-linux-gnu/nvidia; do
    IFS=':' read -r -a parts <<<"$candidate"
    if [[ -d "${parts[0]}" ]]; then
      jetson_ld="$candidate"
      break
    fi
  done

  if [[ -z "${jetson_ld}" ]]; then
    echo "nix_gl_env.sh: Jetson detected but tegra/nvidia GL library dirs are missing — Gazebo rendering may fail." >&2
    return 0
  fi

  export LD_LIBRARY_PATH="${jetson_ld}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  export LUCY_GPU_MODE="${LUCY_GPU_MODE:-jetson}"

  local nvidia_egl=/usr/share/glvnd/egl_vendor.d/10_nvidia.json
  if [[ -z "${__EGL_VENDOR_LIBRARY_FILENAMES:-}" ]] && [[ -f "$nvidia_egl" ]]; then
    export __EGL_VENDOR_LIBRARY_FILENAMES="$nvidia_egl"
  fi
  export __GLX_VENDOR_LIBRARY_NAME="${__GLX_VENDOR_LIBRARY_NAME:-nvidia}"
}

_lucy_prepend_nix_gl() {
  case "${LUCY_NIX_GL:-auto}" in
    0|false|no|off|disable)
      if _lucy_on_nixos; then
        echo "nix_gl_env.sh: LUCY_NIX_GL=0 — host GL libs not prepended; Gazebo may fail on NixOS." >&2
      fi
      return 0
      ;;
  esac

  local wrapper="" candidate nix_ld=""
  if [[ -n "${LUCY_NIX_GL_WRAPPER:-}" ]]; then
    if command -v "${LUCY_NIX_GL_WRAPPER}" &>/dev/null; then
      wrapper="${LUCY_NIX_GL_WRAPPER}"
    fi
  else
    for candidate in nixGLIntel nixGLDefault nixGL; do
      if command -v "${candidate}" &>/dev/null; then
        wrapper="${candidate}"
        break
      fi
    done
  fi

  if [[ -n "${wrapper}" ]]; then
    nix_ld=$("${wrapper}" -- printenv LD_LIBRARY_PATH 2>/dev/null || true)
  fi

  if [[ -z "${nix_ld}" ]] && [[ -d /run/opengl-driver/lib ]]; then
    nix_ld="/run/opengl-driver/lib"
  fi

  [[ -n "${nix_ld}" ]] || {
    if _lucy_on_nixos; then
      echo "nix_gl_env.sh: no nixGL wrapper and /run/opengl-driver/lib missing — install nixGLIntel or enable NixOS opengl drivers." >&2
    fi
    return 0
  }

  export LD_LIBRARY_PATH="${nix_ld}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
}

_lucy_nixos_gazebo_env() {
  local vendor=/run/opengl-driver/share/glvnd/egl_vendor.d/50_mesa.json
  if [[ -z "${__EGL_VENDOR_LIBRARY_FILENAMES:-}" ]] && [[ -f "$vendor" ]]; then
    export __EGL_VENDOR_LIBRARY_FILENAMES="$vendor"
  fi
  export GZ_IP="${GZ_IP:-127.0.0.1}"
}

if lucy_is_jetson; then
  _lucy_prepend_jetson_gl
else
  _lucy_prepend_nix_gl
fi
_lucy_nixos_gazebo_env
