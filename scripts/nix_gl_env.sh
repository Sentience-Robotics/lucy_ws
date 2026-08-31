#!/usr/bin/env bash
# NixOS GL env for Pixi/RoboStack (Gazebo, RViz, rqt).
#
# Pixi activation puts conda Mesa/GLVND first on LD_LIBRARY_PATH; on NixOS +
# Wayland that breaks gz sim (GLX errors, "requesting world names", hung spawners).
# This script runs *inside* pixi run and:
#   1. Prepends host GL libs (nixGL wrapper, or /run/opengl-driver/lib)
#   2. Sets Mesa EGL vendor + GZ_IP for OGRE / Gazebo transport
#
# Usage (via scripts/pixi_lucy_launch.sh or python -m launcher):
#   pixi run sim
#
# Do not set LUCY_NIX_GL=0 on NixOS — EGL vars alone are not enough.
# Override wrapper (AMD/NVIDIA): LUCY_NIX_GL_WRAPPER=nixGLIntel

_lucy_on_nixos() {
  [[ -d /run/opengl-driver ]] || [[ -n "${LUCY_NIXOS:-}" ]]
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
  if [[ -f "$vendor" ]]; then
    export __EGL_VENDOR_LIBRARY_FILENAMES="$vendor"
  fi
  export GZ_IP="${GZ_IP:-127.0.0.1}"
}

_lucy_prepend_nix_gl
_lucy_nixos_gazebo_env
