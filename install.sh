#!/usr/bin/env bash
# Lucy workspace setup: clone sub-repos, install RoboStack deps via Pixi, colcon build.
#
# Usage:
#   ./install.sh                     clone/pull repos + pixi install + build
#   ./install.sh --update | update   same as above
#   ./install.sh --repair              wipe build/install/log, re-clone src repos, re-lock Pixi
#   ./install.sh --build-only        skip git; pixi run build + panel-install
#   ./install.sh --skip-build        clone/pull only (CI)
#
# Optional .env: DEV=true uses url_ssh from repos config.
# Optional config/repos.json.local overrides config/repos.json.
#
# Pixi: install.sh requires pixi ≥ LUCY_PIXI_MIN_VERSION (default 0.78.0). When pixi
# is missing or too old, it can install/upgrade via https://pixi.sh/install.sh
# (curl | bash). Interactive shells prompt first; set LUCY_PIXI_AUTO_UPGRADE=1 to
# skip the prompt (CI, Lucy.py). Set LUCY_SKIP_PIXI_UPGRADE=1 to fail instead.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer user-local Pixi (official installer) over distro/nix packages.
export PATH="${HOME}/.pixi/bin:${PATH}"

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

ensure_pixi() {
  local ver min="${LUCY_PIXI_MIN_VERSION:-0.78.0}"

  if command -v pixi &>/dev/null; then
    ver="$(pixi --version 2>/dev/null | awk '{print $2}')"
    if [ -n "$ver" ] && printf '%s\n%s\n' "$min" "$ver" | sort -C -V; then
      return 0
    fi
  else
    ver=""
  fi

  if [ "${LUCY_SKIP_PIXI_UPGRADE:-}" = "1" ]; then
    if [ -z "$ver" ]; then
      echo "install.sh: pixi not found." >&2
    else
      echo "install.sh: pixi $ver is older than required $min." >&2
    fi
    echo "Install/upgrade: curl -fsSL https://pixi.sh/install.sh | bash" >&2
    exit 1
  fi

  if ! command -v curl &>/dev/null; then
    if [ -z "$ver" ]; then
      echo "install.sh: pixi not found; curl is required to install it." >&2
    else
      echo "install.sh: pixi $ver is older than required $min (multi-platform lock needs newer pixi)." >&2
    fi
    echo "Install/upgrade: curl -fsSL https://pixi.sh/install.sh | bash" >&2
    exit 1
  fi

  if [ -n "$ver" ]; then
    echo "install.sh: pixi $ver is older than $min — installing latest via pixi.sh ..."
    echo "install.sh: (set LUCY_SKIP_PIXI_UPGRADE=1 to abort; LUCY_PIXI_AUTO_UPGRADE=1 to skip prompt)" >&2
  else
    echo "install.sh: pixi not found — installing via pixi.sh ..."
    echo "install.sh: (set LUCY_SKIP_PIXI_UPGRADE=1 to abort; LUCY_PIXI_AUTO_UPGRADE=1 to skip prompt)" >&2
  fi
  confirm_pixi_install
  curl -fsSL https://pixi.sh/install.sh | bash
  export PATH="${HOME}/.pixi/bin:${PATH}"

  if ! command -v pixi &>/dev/null; then
    echo "install.sh: pixi install finished but pixi is not on PATH." >&2
    echo 'Add to your shell profile: export PATH="$HOME/.pixi/bin:$PATH"' >&2
    exit 1
  fi

  ver="$(pixi --version 2>/dev/null | awk '{print $2}')"
  if [ -z "$ver" ] || ! printf '%s\n%s\n' "$min" "$ver" | sort -C -V; then
    echo "install.sh: pixi $ver still below $min after install." >&2
    exit 1
  fi
}

confirm_pixi_install() {
  case "$(echo "${LUCY_PIXI_AUTO_UPGRADE:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
  esac
  case "$(echo "${CI:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
  esac
  if [ ! -t 0 ]; then
    echo "install.sh: pixi install/upgrade needs confirmation in non-interactive mode." >&2
    echo "Set LUCY_PIXI_AUTO_UPGRADE=1 or run from an interactive terminal." >&2
    exit 1
  fi
  printf 'Install/upgrade pixi via https://pixi.sh/install.sh? [y/N] ' >&2
  read -r reply
  case "$reply" in
    y|Y|yes|Yes|YES) return 0 ;;
    *)
      echo "install.sh: aborted — install pixi manually or set LUCY_PIXI_AUTO_UPGRADE=1." >&2
      exit 1
      ;;
  esac
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

def clean(s):
    return str(s).strip().strip('\r\n')

use_ssh = os.environ.get('DEV', '').strip().lower() in ('1', 'true', 'yes')

with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = clean(r.get('name', ''))
    branch = clean(r.get('branch', 'main'))
    url_https = clean(r.get('url_https') or r.get('url') or '')
    url_ssh = clean(r.get('url_ssh') or '')
    url = (url_ssh or url_https) if use_ssh else (url_https or url_ssh)
    optional = 1 if r.get('optional') else 0
    if name and url:
        print(name, branch, url, optional, sep='\t')
" "$CONFIG_FILE"
}

mark_optional_colcon_ignore() {
  case "$(echo "${LUCY_BUILD_OPTIONAL:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
  esac
  while IFS=$'\t' read -r name _ _ optional; do
    name="${name//$'\r'/}"
    optional="${optional//$'\r'/}"
    if [ "$optional" = "1" ] && [ -d "src/${name}" ]; then
      echo "install.sh: skipping colcon build for optional repo ${name} (COLCON_IGNORE; set LUCY_BUILD_OPTIONAL=1 to build)"
      touch "src/${name}/COLCON_IGNORE"
    fi
  done < <(parse_repos)
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
  ensure_pixi
  pixi_workspace_build
  echo "Build complete. Run './launch_lucy.sh' or Launch in Lucy.py"
  exit 0
fi

ensure_pixi
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
  while IFS=$'\t' read -r name _ _ _optional; do
    remove_workspace_src_repo "$name"
  done < <(parse_repos)
  echo "Repair: re-solving Pixi lock (pixi lock) ..."
  pixi lock
fi

case "$(echo "${DEV:-}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes) echo "DEV=true: using url_ssh from repos config." ;;
esac

mkdir -p src
while IFS=$'\t' read -r name branch url optional; do
  name="${name//$'\r'/}"
  branch="${branch//$'\r'/}"
  url="${url//$'\r'/}"
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

mark_optional_colcon_ignore

pixi_workspace_build
echo "Install complete. Run './launch_lucy.sh' or Launch in Lucy.py"
