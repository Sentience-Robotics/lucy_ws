#!/usr/bin/env bash
# One-time setup for the Lucy workspace.
#
# Clones the sub-repositories listed in config/repos.json into ./src/, builds the
# Docker image (lucy_ros2:humble), and runs `rosdep install`, `colcon build`
# and `yarn install` for the control panel — all inside that container.
#
# Run from the workspace root (directory containing this script).
#
# Usage:
#   ./install.sh                     clone missing repos, pull existing ones, rebuild workspace
#   ./install.sh --update | update   same as above (explicit)
#   ./install.sh --repair            wipe each repo under src/ then re-clone and rebuild
#   ./install.sh --build-only        skip git; rebuild the workspace inside the container
#   ./install.sh --arm               build/run the image as linux/arm64 (Apple Silicon)
#                                    combine with any other flag, e.g. --arm --build-only
#
# Optional .env (copy from .env.example): DEV=true selects `url_ssh` in repos.json (default: `url_https`).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

# Container image + workspace mount path (must match Dockerfile.humble WORKDIR).
IMAGE_NAME="lucy_ros2:humble"
DOCKERFILE_PATH="$SCRIPT_DIR/Dockerfile.humble"
WORKSPACE="/workspace"
CONFIG_FILE="${SCRIPT_DIR}/config/repos.json"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/docker/ensure_image.sh"

ensure_docker_image() {
  ensure_lucy_docker_image "$SCRIPT_DIR" "$IMAGE_NAME" "$DOCKERFILE_PATH"
}

# ----------------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------------

# Extract --arm anywhere on the command line (it can be combined with any other flag).
INSTALL_USE_ARM_IMAGE=0
_install_argv=()
for _a in "$@"; do
  if [ "$_a" = "--arm" ]; then
    INSTALL_USE_ARM_IMAGE=1
  else
    _install_argv+=("$_a")
  fi
done
set -- "${_install_argv[@]}"

# `.lucy-docker-platform` is read by docker/ensure_image.sh and launch_lucy.sh
# so a one-time `--arm` install keeps subsequent runs on arm64.
DOCKER_PLATFORM_FILE="$SCRIPT_DIR/.lucy-docker-platform"
if [ "$INSTALL_USE_ARM_IMAGE" = 1 ]; then
  printf '%s\n' "linux/arm64" >"$DOCKER_PLATFORM_FILE"
  echo "Using linux/arm64 for Docker build/run (recorded in .lucy-docker-platform)."
else
  rm -f "$DOCKER_PLATFORM_FILE"
fi

MODE="install"
case "${1:-}" in
  --build-only) MODE="build-only"; shift ;;
  --repair)     MODE="repair";     shift ;;
  --update | update) shift ;;
esac
if [ $# -gt 0 ]; then
  echo "Unknown argument: $1 (try --arm, --repair, --update, or --build-only)" >&2
  exit 1
fi

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1. Install it and run install.sh again." >&2
    exit 1
  fi
}

# Wipe src/<name>. We delete from inside the container too because colcon and
# Python may have created root-owned files (__pycache__, install/) on the bind mount.
remove_workspace_src_repo() {
  local name="$1"
  rm -rf "src/${name}" 2>/dev/null || true
  docker_run_platform_flags "$SCRIPT_DIR"
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" --rm \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "$IMAGE_NAME" -c "rm -rf ${WORKSPACE}/src/${name}"
}

update_git_repo() {
  local name="$1" branch="$2"
  local dir="src/${name}"
  echo "Updating ${name} (branch ${branch}) ..."
  git -C "$dir" fetch origin
  if ! git -C "$dir" checkout "$branch"; then
    git -C "$dir" checkout -b "$branch" "origin/${branch}"
  fi
  if ! git -C "$dir" pull --ff-only origin "$branch"; then
    echo "install.sh: cannot fast-forward ${name} on ${branch}. Merge/rebase locally or run ./install.sh --repair" >&2
    exit 1
  fi
}

# Reads config/repos.json and prints one `name<TAB>branch<TAB>url` per repo.
# Picks `url_ssh` when DEV=true, else `url_https` (falls back to the other field, then legacy `url`).
parse_repos() {
  python3 -c "
import json, os, sys

use_ssh = os.environ.get('DEV', '').strip().lower() in ('1', 'true', 'yes')

with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = r.get('name', '').strip()
    branch = r.get('branch', 'main').strip()
    url_https = (r.get('url_https') or r.get('url') or '').strip()
    url_ssh = (r.get('url_ssh') or '').strip()
    url = (url_ssh or url_https) if use_ssh else (url_https or url_ssh)
    if name and url:
        print(name, branch, url, sep='\t')
" "$CONFIG_FILE"
}

# rosdep install + colcon build + yarn install for the control panel, all inside the container.
# `camera_ros` is wiped because rosdep flips between PEP517/sdist builds depending on the host
# (Python wheels), and colcon does not always detect that as a reason to rebuild.
docker_workspace_install() {
  ensure_docker_image
  docker_run_platform_flags "$SCRIPT_DIR"
  docker_run_it_flags
  echo "Docker install: rosdep, colcon build, yarn install (lucy_control_panel) ..."
  local inner_cmd
  read -r -d '' inner_cmd <<'EOS' || true
source /opt/ros/humble/setup.bash \
  && cd /workspace \
  && rosdep install --from-paths src --ignore-src -r -y --skip-keys="audio_common micro_ros_agent" \
  && rm -rf build/camera_ros install/camera_ros \
  && colcon build \
  && if [ -f src/lucy_control_panel/package.json ]; then \
       ( cd src/lucy_control_panel && yarn install ); \
     fi
EOS
  docker run "${DOCKER_RUN_PLATFORM_ARGS[@]}" "${DOCKER_RUN_IT[@]}" --rm \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "$IMAGE_NAME" -c "$inner_cmd"
}

# ----------------------------------------------------------------------------
# 1. --build-only short-circuit (no git, no host requirements beyond docker)
# ----------------------------------------------------------------------------

if [ "$MODE" = "build-only" ]; then
  check_cmd docker
  docker_workspace_install
  echo "Build complete. Run ./launch_lucy.sh to start the stack."
  exit 0
fi

# ----------------------------------------------------------------------------
# 2. Host requirements
# ----------------------------------------------------------------------------

check_cmd docker
check_cmd git
check_cmd python3
if [ "${CI:-}" = "true" ] || [ "${CI:-}" = "1" ] || [ "${LUCY_INSTALL_SKIP_XHOST:-}" = "1" ]; then
  echo "install.sh: skipping xhost check (set CI=1 for headless CI or export LUCY_INSTALL_SKIP_XHOST=1 locally)."
else
  check_cmd xhost
fi
echo "Requirements OK (docker, git, python3)."

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Config not found: $CONFIG_FILE" >&2
  echo "Set name, branch, url_https and url_ssh for each repo." >&2
  exit 1
fi
if [ "$(parse_repos | wc -l)" -eq 0 ]; then
  echo "No repos with name and url_https/url_ssh in $CONFIG_FILE" >&2
  exit 1
fi

# ----------------------------------------------------------------------------
# 3. (Optional) --repair: wipe every src/<repo> before re-cloning
# ----------------------------------------------------------------------------

if [ "$MODE" = "repair" ]; then
  echo "Repair: removing listed repos under src/ ..."
  ensure_docker_image
  while IFS=$'\t' read -r name _ _; do
    remove_workspace_src_repo "$name"
  done < <(parse_repos)
fi

# ----------------------------------------------------------------------------
# 4. Clone missing repos / fast-forward existing ones
# ----------------------------------------------------------------------------

case "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) echo "DEV=true: using url_ssh from config/repos.json." ;;
esac
mkdir -p src
while IFS=$'\t' read -r name branch url; do
  if [ ! -d "src/${name}/.git" ]; then
    if [ -e "src/${name}" ]; then
      echo "Removing stale src/${name} (not a usable git clone; git refuses non-empty paths) ..."
      ensure_docker_image
      remove_workspace_src_repo "$name"
    fi
    echo "Cloning ${name} into src/${name} (branch: ${branch}) ..."
    git clone -b "$branch" "$url" "src/${name}"
  else
    update_git_repo "$name" "$branch"
  fi
done < <(parse_repos)

# ----------------------------------------------------------------------------
# 5. Build the workspace inside the container
# ----------------------------------------------------------------------------

docker_workspace_install
echo "Install complete. Run ./launch_lucy.sh to start the stack."
