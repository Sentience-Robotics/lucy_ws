#!/usr/bin/env bash
# Install the Lucy RP2040 udev rule for serial port access on Linux without dialout group requirements.
#
# Usage:
#   ./scripts/setup_udev.sh
#   # or: pixi run setup-udev

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RULE_NAME="99-lucy-rp2040.rules"
SOURCE_RULE="${WORKSPACE_ROOT}/config/udev/${RULE_NAME}"
TARGET_DIR="/etc/udev/rules.d"
TARGET_FILE="${TARGET_DIR}/${RULE_NAME}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "udev rules are only applicable on Linux. Current OS: $(uname -s)"
  exit 0
fi

if [[ ! -f "$SOURCE_RULE" ]]; then
  echo "Error: source rule not found at $SOURCE_RULE" >&2
  exit 1
fi

echo "Installing $RULE_NAME to $TARGET_DIR (requires sudo)..."
sudo install -m 0644 "$SOURCE_RULE" "$TARGET_FILE"
if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=tty
fi

echo "Done! The RP2040 udev rule is active. If the board is already plugged in, replug it."
