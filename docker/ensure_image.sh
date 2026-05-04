# shellcheck shell=bash
# Rebuild the Lucy image when Dockerfile.humble or target platform changes (LABEL lucy.dockerfile.sha256 = sha256|platform).
# Tag: lucy_ros2_control:humble. Platform: env LUCY_DOCKER_PLATFORM, else first line of ws_root/.lucy-docker-platform, else host CPU.

lucy_host_container_platform() {
  case "$(uname -m)" in
    x86_64 | amd64) echo linux/amd64 ;;
    aarch64 | arm64) echo linux/arm64 ;;
    *) echo "linux/$(uname -m)" ;;
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

# Sets DOCKER_RUN_PLATFORM_ARGS so docker run matches cross-built images (silences platform mismatch warnings).
docker_run_platform_flags() {
  local ws_root="$1"
  local target host
  target=$(lucy_workspace_target_platform "$ws_root")
  host=$(lucy_host_container_platform)
  DOCKER_RUN_PLATFORM_ARGS=()
  if [[ "$target" != "$host" ]]; then
    DOCKER_RUN_PLATFORM_ARGS=(--platform "$target")
  fi
}

ensure_lucy_docker_image() {
  local ws_root="$1"
  local image_name="${2:-lucy_ros2_control:humble}"
  local dockerfile="${3:-$ws_root/Dockerfile.humble}"
  local hash want want_id
  local target_platform
  local build_platform_args

  if [ ! -f "$dockerfile" ]; then
    echo "ensure_lucy_docker_image: missing $dockerfile" >&2
    return 1
  fi

  target_platform=$(lucy_workspace_target_platform "$ws_root")
  build_platform_args=(--platform "$target_platform")

  hash=$(sha256sum "$dockerfile" | awk '{print $1}')
  want_id="${hash}|${target_platform}"

  if docker image inspect "$image_name" &>/dev/null; then
    want=$(docker image inspect "$image_name" --format '{{index .Config.Labels "lucy.dockerfile.sha256"}}' 2>/dev/null || true)
    if [ "$want" = "$want_id" ]; then
      return 0
    fi
    echo "Lucy Dockerfile or platform changed (label mismatch); rebuilding $image_name ..."
  else
    echo "Building Docker image $image_name ..."
  fi
  docker build "${build_platform_args[@]}" -f "$dockerfile" \
    --build-arg "TARGETPLATFORM=$target_platform" \
    --build-arg "DOCKERFILE_SHA256=$hash" \
    --build-arg "LUCY_DOCKER_BUILD_PLATFORM=$target_platform" \
    -t "$image_name" "$ws_root"
}

# docker run -it breaks without a TTY (e.g. GitHub Actions); use -i only there.
docker_run_it_flags() {
  if [ -n "${CI:-}" ] || ! [ -t 1 ]; then
    DOCKER_RUN_IT=( -i )
  else
    DOCKER_RUN_IT=( -it )
  fi
}
