#!/usr/bin/env bash
# One-time setup: check requirements, clone repositories from config/repos.json into src/, then build in Docker
# (rosdep, colcon, yarn install for lucy_control_panel).
# Run from the workspace root (directory containing this script and launch_lucy.sh).
#
# Optional: copy .env.example to .env — DEV=true rewrites HTTPS clone URLs to SSH (see parse_repos).
#
# Usage:
#   ./install.sh                  # clone missing repos; git pull existing @ repos.json branch + Docker build
#   ./install.sh --update | update  # same as above (explicit update)
#   ./install.sh --repair          # delete listed repos under src/ and re-clone + Docker build
#   ./install.sh --build-only      # Docker build only (skips git)

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

IMAGE_NAME="lucy_ros2:humble"
WORKSPACE="/lucy_ws"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/docker/ensure_image.sh"

ensure_docker_image() {
  ensure_lucy_docker_image "$SCRIPT_DIR" "$IMAGE_NAME"
}

# --- Requirements ---
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1. Install it and run install.sh again." >&2
    exit 1
  fi
}

# Remove src/<repo> on the bind mount (host rm + container rm for root-owned files e.g. __pycache__).
remove_workspace_src_repo() {
  local name="$1"
  rm -rf "src/${name}" 2>/dev/null || true
  docker run --rm -v "$SCRIPT_DIR:$WORKSPACE" "$IMAGE_NAME" -c "rm -rf /workspace/src/${name}"
}

# Fetch + fast-forward to repos.json branch (existing clone).
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

# rosdep + colcon + control panel deps (inside container; workspace mounted at /workspace)
docker_workspace_install() {
  ensure_docker_image
  docker_run_it_flags
  echo "Docker install: rosdep, colcon build, yarn install (lucy_control_panel) ..."
  local inner_cmd
  read -r -d '' inner_cmd <<'EOS' || true
source /opt/ros/humble/setup.bash && cd /workspace && rosdep install --from-paths src --ignore-src -r -y --skip-keys="audio_common micro_ros_agent" && rm -rf build/camera_ros install/camera_ros && colcon build && if [ -f src/lucy_control_panel/package.json ]; then ( cd src/lucy_control_panel && yarn install ); fi
EOS
  docker run "${DOCKER_RUN_IT[@]}" --rm \
    -v "$SCRIPT_DIR:$WORKSPACE" \
    "$IMAGE_NAME" -c "$inner_cmd"
}

if [ "${1:-}" = "--build-only" ]; then
  check_cmd docker
  docker_workspace_install
  echo "Build complete. Run ./launch_lucy.sh to start a shell."
  exit 0
fi

REPAIR=0
case "${1:-}" in
  --repair)
    REPAIR=1
    shift
    ;;
  --update | update)
    shift
    ;;
esac
if [ $# -gt 0 ]; then
  echo "Unknown argument: $1 (try --repair, --update, or --build-only)" >&2
  exit 1
fi

check_cmd docker
check_cmd git
check_cmd python3
echo "Requirements OK (docker, git, python3)."

# --- Load config ---
CONFIG_FILE="${SCRIPT_DIR}/config/repos.json"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "Config not found: $CONFIG_FILE"
  echo "Copy config/repos.json.example to config/repos.json and set name, branch and url for each repo."
  exit 1
fi

# Parse JSON: output one line per repo: name\tbranch\turl (HTTPS→SSH when DEV=true)
parse_repos() {
  python3 -c "
import json, os, sys
from urllib.parse import urlparse

def dev_clone_ssh():
    v = os.environ.get('DEV', '').strip().lower()
    return v in ('1', 'true', 'yes')

def rewrite_clone_url(url: str) -> str:
    u = url.strip()
    if not dev_clone_ssh():
        return u
    if u.startswith('git@') or u.startswith('ssh://'):
        return u
    if not (u.startswith('http://') or u.startswith('https://')):
        return u
    p = urlparse(u)
    host = (p.hostname or '').lower()
    path = p.path.strip('/')
    if not path:
        return u
    if path.endswith('.git'):
        tail = path
    else:
        tail = path + '.git'
    if host == 'github.com':
        return f'git@github.com:{tail}'
    if host == 'gitlab.com':
        return f'git@gitlab.com:{tail}'
    return u

with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = r.get('name', '').strip()
    branch = r.get('branch', 'main').strip()
    url = rewrite_clone_url(r.get('url', '').strip())
    if name and url:
        print(name, branch, url, sep='\t')
" "$CONFIG_FILE"
}

REPO_COUNT=$(parse_repos | wc -l)
if [ "$REPO_COUNT" -eq 0 ]; then
  echo "No repos with name and url in config/repos.json."
  exit 1
fi

if [ "$REPAIR" = 1 ]; then
  echo "Repair: removing listed repos under src/ (then re-clone) ..."
  ensure_docker_image
  while IFS=$'\t' read -r name _ _; do
    remove_workspace_src_repo "$name"
  done < <(parse_repos)
fi

# --- Clone or update repos under src/ ---
case "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) echo "DEV=true: using SSH clone URLs (HTTPS entries in repos.json are rewritten)." ;;
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

# --- Build workspace in Docker, then exit ---
docker_workspace_install
echo "Install complete. Run ./launch_lucy.sh to start a shell."
