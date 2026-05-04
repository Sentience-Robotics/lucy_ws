# shellcheck shell=bash
# Rebuild the Lucy image when Dockerfile.humble or target platform changes (LABEL lucy.dockerfile.sha256 = sha256|platform).
# Tag: lucy_ros2_control:humble. Platform: env LUCY_DOCKER_PLATFORM, else first line of ws_root/.lucy-docker-platform, else host default.

ensure_lucy_docker_image() {
  local ws_root="$1"
  local image_name="${2:-lucy_ros2_control:humble}"
  local dockerfile="${3:-$ws_root/Dockerfile.humble}"
  local hash want want_id
  local resolved_platform=""
  local platform_label="default"
  local build_platform_args=()

  if [ ! -f "$dockerfile" ]; then
    echo "ensure_lucy_docker_image: missing $dockerfile" >&2
    return 1
  fi

  if [[ -n "${LUCY_DOCKER_PLATFORM:-}" ]]; then
    resolved_platform="${LUCY_DOCKER_PLATFORM}"
  elif [[ -f "$ws_root/.lucy-docker-platform" ]]; then
    resolved_platform=$(head -1 "$ws_root/.lucy-docker-platform" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  fi
  if [[ -n "$resolved_platform" ]]; then
    platform_label="$resolved_platform"
    build_platform_args=(--platform "$resolved_platform")
  fi

  hash=$(sha256sum "$dockerfile" | awk '{print $1}')
  want_id="${hash}|${platform_label}"

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
    --build-arg "DOCKERFILE_SHA256=$hash" \
    --build-arg "LUCY_DOCKER_BUILD_PLATFORM=$platform_label" \
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
