#!/usr/bin/env bash
# Detect host GPU capabilities and populate Docker flags for Lucy launches.
#
# Source from launch_lucy.sh or install.sh (do not execute directly):
#   source "$SCRIPT_DIR/docker/gpu_detect.sh"
#
# Sets:
#   LUCY_GPU_MODE   — jetson | nvidia | dri | software
#   GPU_DOCKER_ARGS — bash array appended to docker run
#
# Override detection for testing: LUCY_GPU_MODE=software|jetson|nvidia|dri

GPU_DOCKER_ARGS=()
LUCY_GPU_MODE=software

_lucy_is_jetson() {
  if [[ -f /etc/nv_tegra_release ]]; then
    return 0
  fi
  if [[ -r /proc/device-tree/model ]]; then
    tr -d '\0' </proc/device-tree/model 2>/dev/null | grep -qi jetson
    return $?
  fi
  return 1
}

_lucy_docker_has_nvidia_runtime() {
  docker info 2>/dev/null | grep -qiE 'nvidia|Runtimes.*nvidia'
}

_lucy_append_dri_devices() {
  local node
  shopt -s nullglob
  for node in /dev/dri/card* /dev/dri/renderD*; do
    GPU_DOCKER_ARGS+=(--device "$node")
  done
  shopt -u nullglob
}

_lucy_append_render_groups() {
  # Docker resolves group names against the *image* /etc/group, not the host.
  # Pass numeric GIDs from the host so render/video access works in the container.
  local group gid
  for group in render video; do
    gid="$(getent group "$group" 2>/dev/null | awk -F: '{print $3}')"
    [[ -n "$gid" ]] || continue
    GPU_DOCKER_ARGS+=(--group-add "$gid")
  done
}

_lucy_apply_jetson_gpu() {
  LUCY_GPU_MODE=jetson
  if _lucy_docker_has_nvidia_runtime; then
    GPU_DOCKER_ARGS+=(--runtime nvidia)
    GPU_DOCKER_ARGS+=(-e "NVIDIA_VISIBLE_DEVICES=all")
    GPU_DOCKER_ARGS+=(-e "NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute,video")
    GPU_DOCKER_ARGS+=(-e "__GLX_VENDOR_LIBRARY_NAME=nvidia")
    GPU_DOCKER_ARGS+=(-e "__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json")
  else
    echo "GPU: jetson detected but Docker nvidia runtime missing; using software rendering." >&2
    echo "       Install nvidia-container-toolkit for hardware GL in the container." >&2
  fi
  if [[ -d /dev/dri ]]; then
    _lucy_append_dri_devices
    _lucy_append_render_groups
  fi
}

lucy_apply_gpu_detect() {
  GPU_DOCKER_ARGS=()
  LUCY_GPU_MODE=software

  case "$(echo "${LUCY_GPU_MODE_OVERRIDE:-}" | tr '[:upper:]' '[:lower:]')" in
    jetson|nvidia|dri|software)
      LUCY_GPU_MODE="${LUCY_GPU_MODE_OVERRIDE,,}"
      case "$LUCY_GPU_MODE" in
        jetson) _lucy_apply_jetson_gpu ;;
        nvidia)
          GPU_DOCKER_ARGS+=(--gpus all)
          GPU_DOCKER_ARGS+=(-e "NVIDIA_VISIBLE_DEVICES=all")
          GPU_DOCKER_ARGS+=(-e "NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute,video")
          GPU_DOCKER_ARGS+=(-e "__GLX_VENDOR_LIBRARY_NAME=nvidia")
          GPU_DOCKER_ARGS+=(-e "__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json")
          ;;
        dri)
          _lucy_append_dri_devices
          _lucy_append_render_groups
          ;;
      esac
      return 0
      ;;
  esac

  if _lucy_is_jetson; then
    _lucy_apply_jetson_gpu
    return 0
  fi

  if command -v nvidia-smi >/dev/null 2>&1 && _lucy_docker_has_nvidia_runtime; then
    if nvidia-smi >/dev/null 2>&1; then
      LUCY_GPU_MODE=nvidia
      GPU_DOCKER_ARGS+=(--gpus all)
      GPU_DOCKER_ARGS+=(-e "NVIDIA_VISIBLE_DEVICES=all")
      GPU_DOCKER_ARGS+=(-e "NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute,video")
      GPU_DOCKER_ARGS+=(-e "__GLX_VENDOR_LIBRARY_NAME=nvidia")
      GPU_DOCKER_ARGS+=(-e "__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json")
      return 0
    fi
  fi

  if [[ -d /dev/dri ]] && compgen -G '/dev/dri/renderD*' >/dev/null 2>&1; then
    LUCY_GPU_MODE=dri
    _lucy_append_dri_devices
    _lucy_append_render_groups
    return 0
  fi

  LUCY_GPU_MODE=software
}

lucy_gpu_launch_message() {
  case "$LUCY_GPU_MODE" in
    jetson)
      if _lucy_docker_has_nvidia_runtime; then
        echo "GPU: jetson (nvidia container runtime + /dev/dri when available)"
      else
        echo "GPU: jetson (software fallback — nvidia runtime not configured)"
      fi
      ;;
    nvidia) echo "GPU: nvidia (hardware acceleration enabled)" ;;
    dri)    echo "GPU: dri (Mesa /dev/dri passthrough)" ;;
    *)      echo "GPU: software (VNC llvmpipe or headless rendering)" ;;
  esac
}

# Pick a host DISPLAY when unset so Jetson can use native X11 + GPU instead of VNC/llvmpipe.
lucy_resolve_host_display() {
  [[ -n "${DISPLAY:-}" ]] && return 0

  local sock n
  shopt -s nullglob
  for sock in /tmp/.X11-unix/X[0-9]*; do
    n="${sock##*/X}"
    DISPLAY=":${n}"
    export DISPLAY
    shopt -u nullglob
    echo "GUI: auto-selected DISPLAY=$DISPLAY (local X11 socket)" >&2
    return 0
  done
  shopt -u nullglob
}

# When sourced, apply immediately unless caller sets LUCY_GPU_DETECT_DEFER=1.
if [[ "${BASH_SOURCE[0]}" != "${0}" ]] && [[ "${LUCY_GPU_DETECT_DEFER:-}" != 1 ]]; then
  lucy_apply_gpu_detect
fi
