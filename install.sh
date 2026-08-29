#!/usr/bin/env bash
# Lucy workspace setup: clone sub-repos, install RoboStack deps via Pixi, colcon build.
#
# Usage:
#   ./install.sh                     clone/pull repos + pixi install + build
#   ./install.sh --update | update   same as above
#   ./install.sh --repair              wipe build/install/log + re-clone src repos
#   ./install.sh --build-only        skip git; pixi run build + panel-install
#   ./install.sh --skip-build        clone/pull only (CI)
#
# Optional .env: DEV=true uses url_ssh from repos config.
# Optional config/repos.json.local overrides config/repos.json.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

CONFIG_FILE="${SCRIPT_DIR}/config/repos.json"
if [ -f "${SCRIPT_DIR}/config/repos.json.local" ]; then
  CONFIG_FILE="${SCRIPT_DIR}/config/repos.json.local"
  echo "install.sh: using local repo override config/repos.json.local"
fi

SKIP_BUILD=0
MODE="install"
_install_argv=()
for _a in "$@"; do
  case "$_a" in
    --skip-build) SKIP_BUILD=1 ;;
    --build-only) MODE="build-only" ;;
    --repair) MODE="repair" ;;
    --update|update) ;;
    *)
      if [ "$_a" != "--skip-build" ]; then
        _install_argv+=("$_a")
      fi
      ;;
  esac
done
set -- "${_install_argv[@]}"
if [ $# -gt 0 ]; then
  echo "Unknown argument: $1 (try --repair, --update, --build-only, or --skip-build)" >&2
  exit 1
fi

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1." >&2
    echo "Install Pixi: https://pixi.prefix.dev/latest/installation/ (≥ 0.78 recommended)" >&2
    exit 1
  fi
}

check_pixi_version() {
  local ver min="${LUCY_PIXI_MIN_VERSION:-0.78.0}"
  ver="$(pixi --version 2>/dev/null | awk "{print \$2}")"
  if [ -z "$ver" ]; then
    echo "install.sh: could not read pixi version." >&2
    exit 1
  fi
  if ! printf '%s\n%s\n' "$min" "$ver" | sort -C -V; then
    echo "install.sh: pixi $ver is older than recommended $min (multi-platform lock needs newer pixi)." >&2
    echo "Upgrade: curl -fsSL https://pixi.sh/install.sh | bash" >&2
    exit 1
  fi
}

remove_workspace_src_repo() {
  local name="$1"
  rm -rf "src/${name}"
}

update_git_repo() {
  local name="$1" branch="$2" url="$3"
  local dir="src/${name}"
  echo "Updating ${name} (branch ${branch}) ..."
  local current_url
  current_url="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
  if [ "$current_url" != "$url" ]; then
    echo "install.sh: updating origin remote for ${name} -> ${url}"
    git -C "$dir" remote set-url origin "$url"
  fi
  git -C "$dir" fetch origin
  if ! git -C "$dir" checkout "$branch"; then
    git -C "$dir" checkout -b "$branch" "origin/${branch}"
  fi
  if ! git -C "$dir" pull --ff-only origin "$branch"; then
    echo "install.sh: cannot fast-forward ${name} on ${branch}. Merge/rebase locally or run ./install.sh --repair" >&2
    exit 1
  fi
}

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

pixi_install() {
  echo "Pixi install (RoboStack Jazzy, all workspace platforms) ..."
  if [ ! -f "${SCRIPT_DIR}/pixi.lock" ]; then
    echo "No pixi.lock — running pixi lock (solves every platform in pixi.toml) ..."
    pixi lock
  fi
  pixi install
}

build_local_realsense_optional() {
  case "$(echo "${LUCY_BUILD_REALSENSE:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes)
      echo "LUCY_BUILD_REALSENSE enabled — building librealsense locally ..."
      bash "${SCRIPT_DIR}/scripts/build_local_realsense.sh"
      ;;
    *)
      echo "RealSense: local build when needed — ./scripts/build_local_realsense.sh"
      ;;
  esac
}

pixi_workspace_build() {
  pixi_install
  if [ "$SKIP_BUILD" = 1 ]; then
    echo "Skipping workspace build (--skip-build)."
    return 0
  fi
  echo "Building ROS workspace (colcon) ..."
  pixi run build
  echo "Installing control panel dependencies (yarn) ..."
  pixi run panel-install
  build_local_realsense_optional
}

if [ "$MODE" = "build-only" ]; then
  check_cmd pixi
  check_pixi_version
  pixi_workspace_build
  echo "Build complete. Run './launch_lucy.sh' or Launch in Lucy.py"
  exit 0
fi

check_cmd pixi
check_pixi_version
check_cmd git
check_cmd python3
echo "Requirements OK (pixi, git, python3)."

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Config not found: $CONFIG_FILE" >&2
  exit 1
fi
if [ "$(parse_repos | wc -l)" -eq 0 ]; then
  echo "No repos with name and url in $CONFIG_FILE" >&2
  exit 1
fi

if [ "$MODE" = "repair" ]; then
  echo "Repair: removing colcon artifacts (build/, install/, log/) ..."
  rm -rf build install log
  echo "Repair: removing listed repos under src/ ..."
  while IFS=$'\t' read -r name _ _; do
    remove_workspace_src_repo "$name"
  done < <(parse_repos)
fi

case "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) echo "DEV=true: using url_ssh from repos config." ;;
esac

mkdir -p src
while IFS=$'\t' read -r name branch url; do
  if [ ! -d "src/${name}/.git" ]; then
    if [ -e "src/${name}" ]; then
      echo "Removing stale src/${name} ..."
      remove_workspace_src_repo "$name"
    fi
    echo "Cloning ${name} into src/${name} (branch: ${branch}) ..."
    git clone -b "$branch" "$url" "src/${name}"
  else
    update_git_repo "$name" "$branch" "$url"
  fi
done < <(parse_repos)

pixi_workspace_build
echo "Install complete. Run './launch_lucy.sh' or Launch in Lucy.py"
