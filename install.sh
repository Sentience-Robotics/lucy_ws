#!/usr/bin/env bash
# One-time setup: check requirements, clone repositories from config/repos.json into src/, then launch Lucy (Docker).
# Run from the workspace root (directory containing this script and launch_lucy.sh).
#
# Copy config/repos.json.example to config/repos.json and set name, branch and url for each repo.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Requirements ---
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "Missing required command: $1. Install it and run install.sh again." >&2
    exit 1
  fi
}
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

# Parse JSON: output one line per repo: name\tbranch\turl
parse_repos() {
  python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = r.get('name', '').strip()
    branch = r.get('branch', 'main').strip()
    url = r.get('url', '').strip()
    if name and url:
        print(name, branch, url, sep='\t')
" "$CONFIG_FILE"
}

REPO_COUNT=$(parse_repos | wc -l)
if [ "$REPO_COUNT" -eq 0 ]; then
  echo "No repos with name and url in config/repos.json."
  exit 1
fi

# --- Already done? (all listed repos present) ---
ALREADY_DONE=1
while IFS=$'\t' read -r name _ _; do
  [ ! -d "src/${name}/.git" ] && ALREADY_DONE=0 && break
done < <(parse_repos)

if [ "$ALREADY_DONE" = 1 ]; then
  echo "Workspace install appears complete (all repos in config already cloned)."
  printf "Repair (re-clone and re-build) or abort? [y/N] "
  read -r reply
  case "${reply}" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 0 ;;
  esac
  echo "Removing cloned repos in src/ ..."
  while IFS=$'\t' read -r name _ _; do
    rm -rf "src/${name}"
  done < <(parse_repos)
fi

# --- Clone into src/ ---
mkdir -p src
while IFS=$'\t' read -r name branch url; do
  if [ ! -d "src/${name}/.git" ]; then
    echo "Cloning ${name} into src/${name} (branch: ${branch}) ..."
    git clone -b "$branch" "$url" "src/${name}"
  else
    echo "src/${name} already present, skipping clone."
  fi
done < <(parse_repos)

# --- Build workspace in Docker, then exit ---
./launch_lucy.sh --install
echo "Install complete. Run ./launch_lucy.sh to start a shell."
