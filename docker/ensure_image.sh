# shellcheck shell=bash
# Helpers shared by install.sh and launch_lucy.sh:
#
#   ensure_lucy_docker_image   build (or rebuild) the lucy_ros2:humble image
#                              when Dockerfile.humble or the target platform changes.
#   docker_run_platform_flags  populate DOCKER_RUN_PLATFORM_ARGS for `docker run`.
#   docker_run_it_flags        populate DOCKER_RUN_IT (-it locally, -i in CI / no TTY).
#
# Target platform priority:
#   1. $LUCY_DOCKER_PLATFORM
#   2. first line of <ws_root>/.lucy-docker-platform  (written by `./install.sh --arm`)
#   3. host CPU architecture (linux/amd64 or linux/arm64)
#
# Rebuild detection:
#   Each built image is stamped with LABEL lucy.dockerfile.sha256="<sha256>|<platform>".
#   When that label does not match the current Dockerfile sha + target platform,
#   the image is rebuilt; otherwise the existing image is reused.

lucy_host_container_platform() {
  case "$(uname -m)" in
    x86_64 | amd64)  echo linux/amd64 ;;
    aarch64 | arm64) echo linux/arm64 ;;
    *)               echo "linux/$(uname -m)" ;;
  esac
}

lucy_workspace_target_platform() {
  local ws_root="$1"
  local v
  if [[ -n "${LUCY_DOCKER_PLATFORM:-}" ]]; then
    echo "${LUCY_DOCKER_PLATFORM}"
    return
  fi
  if [[ -f "$ws_root/.lucy-docker-platform" ]]; then
    v=$(head -1 "$ws_root/.lucy-docker-platform" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [[ -n "$v" ]]; then
      echo "$v"
      return
    fi
  fi
  lucy_host_container_platform
}

# Always pass --platform on `docker run` so the daemon never guesses
# (avoids the "no specific platform was requested" warning vs. image arch).
docker_run_platform_flags() {
  local ws_root="$1"
  DOCKER_RUN_PLATFORM_ARGS=(--platform "$(lucy_workspace_target_platform "$ws_root")")
}

ensure_lucy_docker_image() {
  local ws_root="$1"
  local image_name="${2:-lucy_ros2:humble}"
  local dockerfile="${3:-$ws_root/Dockerfile.humble}"
  local target_platform base_image bootstrap_desktop install_vnc
  local hash want want_id
  local build_platform_args

  dockerfile_build_hash() {
    awk '
      /^[[:space:]]*#/ { next }
      /^[[:space:]]*$/ { next }
      { sub(/[[:space:]]+$/, "") ; print }
    ' "$1" | sha256sum | awk '{print $1}'
  }

  if [ ! -f "$dockerfile" ]; then
    echo "ensure_lucy_docker_image: missing $dockerfile" >&2
    return 1
  fi

  target_platform=$(lucy_workspace_target_platform "$ws_root")
  build_platform_args=(--platform "$target_platform")

  # osrf/ros:humble-desktop is amd64-only on Docker Hub; on arm64 we use the
  # multi-arch ros:humble-ros-base-jammy + apt-install ros-humble-desktop in the
  # Dockerfile (LUCY_BOOTSTRAP_DESKTOP=1).
  case "$target_platform" in
    linux/arm64)
      base_image="ros:humble-ros-base-jammy"
      bootstrap_desktop=1
      ;;
    *)
      base_image="osrf/ros:humble-desktop"
      bootstrap_desktop=0
      ;;
  esac

  # VNC virtual-desktop tooling: installed on arm64, or forced on any arch with
  # LUCY_FORCE_VNC=1 (lets an amd64 host try the VNC path). Folded into want_id and
  # the image label below so toggling it forces a rebuild even though the
  # Dockerfile text — the only other rebuild trigger — is unchanged.
  install_vnc=0
  [ "$target_platform" = "linux/arm64" ] && install_vnc=1
  case "$(echo "${LUCY_FORCE_VNC:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) install_vnc=1 ;;
  esac

  hash=$(dockerfile_build_hash "$dockerfile")
  want_id="${hash}|${target_platform}|vnc=${install_vnc}"

  if docker image inspect "$image_name" &>/dev/null; then
    want=$(docker image inspect "$image_name" \
             --format '{{index .Config.Labels "lucy.dockerfile.sha256"}}' 2>/dev/null || true)
    if [ "$want" = "$want_id" ]; then
      return 0
    fi
    echo "Lucy Dockerfile or platform changed; rebuilding $image_name ..."
  else
    echo "Building Docker image $image_name ..."
  fi

  docker build "${build_platform_args[@]}" -f "$dockerfile" \
    --build-arg "LUCY_FROM_PLATFORM=$target_platform" \
    --build-arg "LUCY_BASE_IMAGE=$base_image" \
    --build-arg "LUCY_BOOTSTRAP_DESKTOP=$bootstrap_desktop" \
    --build-arg "LUCY_INSTALL_VNC=$install_vnc" \
    --build-arg "DOCKERFILE_SHA256=$hash" \
    --build-arg "LUCY_DOCKER_BUILD_PLATFORM=$target_platform" \
    -t "$image_name" "$ws_root"
}

# `docker run -it` fails without a TTY (e.g. GitHub Actions); fall back to `-i`.
docker_run_it_flags() {
  if [ -n "${CI:-}" ] || ! [ -t 1 ]; then
    DOCKER_RUN_IT=(-i)
  else
    DOCKER_RUN_IT=(-it)
  fi
}
