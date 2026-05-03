# shellcheck shell=bash
# Rebuild lucy_ros2_control:humble when Dockerfile.humble content changes (image LABEL tracks checksum).

ensure_lucy_docker_image() {
  local ws_root="$1"
  local image_name="${2:-lucy_ros2_control:humble}"
  local dockerfile="$ws_root/Dockerfile.humble"
  local hash want

  if [ ! -f "$dockerfile" ]; then
    echo "ensure_lucy_docker_image: missing $dockerfile" >&2
    return 1
  fi
  hash=$(sha256sum "$dockerfile" | awk '{print $1}')
  if docker image inspect "$image_name" &>/dev/null; then
    want=$(docker image inspect "$image_name" --format '{{index .Config.Labels "lucy.dockerfile.sha256"}}' 2>/dev/null || true)
    if [ "$want" = "$hash" ]; then
      return 0
    fi
    echo "Dockerfile.humble changed (label mismatch); rebuilding $image_name ..."
  else
    echo "Building Docker image $image_name ..."
  fi
  docker build -f "$dockerfile" --build-arg "DOCKERFILE_SHA256=$hash" -t "$image_name" "$ws_root"
}

# docker run -it breaks without a TTY (e.g. GitHub Actions); use -i only there.
docker_run_it_flags() {
  if [ -n "${CI:-}" ] || ! [ -t 1 ]; then
    DOCKER_RUN_IT=( -i )
  else
    DOCKER_RUN_IT=( -it )
  fi
}
