#!/usr/bin/env bash
# Link workspace-built dylibs into the Pixi env lib dir (macOS only).
#
# rmw dlopen()s typesupport libraries by bare name, so they must be on the
# dynamic loader's search path. DYLD_LIBRARY_PATH cannot carry them reliably:
# macOS strips DYLD_* on every exec of a SIP-protected binary, and the stack goes
# through several. Measured on macOS 26:
#
#     /usr/bin/env   STRIPPED      pixi python3   SURVIVES
#     /bin/sh -c     STRIPPED      python.org     SURVIVES
#     /bin/bash -c   STRIPPED
#
# rosbridge is reached through both /bin/sh (ExecuteProcess shell=True) and
# /usr/bin/env (its `#!/usr/bin/env python3` shebang), so it always loses the
# variable and fails with "failed to create client: type_support is null" for
# workspace messages — while nodes launched with an absolute shebang keep it.
#
# The Pixi env lib dir is already on the loader's rpath search (it appears in
# dlopen's "tried:" list with no DYLD set), so a symlink there resolves for every
# process regardless of how many protected binaries it was exec'd through.
#
# Idempotent, and only ever touches symlinks it owns — a real file from the conda
# env is never replaced. Re-run after each build (wired into the `build` task).

set -euo pipefail

[[ "$(uname -s)" == "Darwin" ]] || exit 0

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB_DIR="${CONDA_PREFIX:-${WS}/.pixi/envs/default}/lib"

if [[ ! -d "${LIB_DIR}" ]]; then
  echo "macos_link_workspace_libs.sh: ${LIB_DIR} not found — skipping." >&2
  exit 0
fi

# Only rosidl typesupport artifacts are dlopen'd by bare name and so need to be
# here. Two kinds must never be linked in:
#   *_py.dylib   Python bindings, which carry undefined libpython symbols. They
#                resolve fine under the Python interpreter, but exposing them to
#                the C++ loader breaks pluginlib with
#                "symbol not found in flat namespace '_PyExc_RuntimeError'",
#                which stops controller_manager loading its hardware plugin.
#   plugin libs  loaded by pluginlib via an absolute path; they gain nothing here.
_lucy_wants_link() {
  case "$1" in
    *__rosidl_*_py.dylib) return 1 ;;
    *__rosidl_*.dylib) return 0 ;;
    *) return 1 ;;
  esac
}

linked=0
refreshed=0
for src in "${WS}"/install/*/lib/*.dylib; do
  [[ -f "${src}" ]] || continue
  _lucy_wants_link "$(basename "${src}")" || continue
  dst="${LIB_DIR}/$(basename "${src}")"
  if [[ -L "${dst}" ]]; then
    # Only refresh links pointing back into this workspace's install tree.
    case "$(readlink "${dst}")" in
      "${WS}/install/"*) ln -sfn "${src}" "${dst}"; refreshed=$((refreshed + 1)) ;;
    esac
  elif [[ -e "${dst}" ]]; then
    continue  # real file shipped by the conda env — leave it alone
  else
    ln -s "${src}" "${dst}"
    linked=$((linked + 1))
  fi
done

# Drop links whose target disappeared (package removed or renamed) and any this
# script should no longer own, so an older over-broad run is cleaned up in place.
pruned=0
for dst in "${LIB_DIR}"/*.dylib; do
  [[ -L "${dst}" ]] || continue
  case "$(readlink "${dst}")" in
    "${WS}/install/"*)
      if [[ ! -e "${dst}" ]] || ! _lucy_wants_link "$(basename "${dst}")"; then
        rm -f "${dst}"
        pruned=$((pruned + 1))
      fi
      ;;
  esac
done

echo "macos_link_workspace_libs.sh: ${linked} linked, ${refreshed} refreshed, ${pruned} pruned in ${LIB_DIR}"
