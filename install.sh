#!/usr/bin/env bash
# Thin wrapper around install.py, which holds the real (cross-platform) logic.
#
# Usage:
#   ./install.sh                     clone/pull repos + pixi install + build
#   ./install.sh --update | update   same as above
#   ./install.sh --repair            wipe build/install/log, re-clone src repos, re-lock Pixi
#   ./install.sh --build-only        skip git; pixi run build + panel-install
#   ./install.sh --skip-build        clone/pull only (CI)
#
# On Windows use install.py directly: python install.py [same flags]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# "update" as a bare word predates the flags; install.py only knows --update.
args=()
for a in "$@"; do
  case "$a" in
    update) args+=("--update") ;;
    *) args+=("$a") ;;
  esac
done

for py in python3 python; do
  if command -v "$py" &>/dev/null; then
    exec "$py" "${SCRIPT_DIR}/install.py" "${args[@]}"
  fi
done

echo "install.sh: python3 not found. Install Python 3: https://www.python.org/downloads/" >&2
exit 1
