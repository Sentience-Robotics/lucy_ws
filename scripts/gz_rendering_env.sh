#!/usr/bin/env bash
# Version-agnostic gz-rendering plugin + ogre2 resource paths for conda/RoboStack.
# Sourced from pixi [target.linux.activation] on Linux hosts.

[[ -n "${CONDA_PREFIX:-}" ]] || return 0 2>/dev/null || exit 0

if [[ -z "${GZ_RENDERING_PLUGIN_PATH:-}" ]]; then
  for plugin_dir in "$CONDA_PREFIX"/lib/gz-rendering-*/engine-plugins; do
    if [[ -d "$plugin_dir" ]]; then
      export GZ_RENDERING_PLUGIN_PATH="$plugin_dir"
      break
    fi
  done
fi

if [[ -z "${GZ_RENDERING_RESOURCE_PATH:-}" ]]; then
  for resource_root in "$CONDA_PREFIX"/share/gz/gz-rendering*; do
    if [[ -d "$resource_root/ogre2" ]]; then
      export GZ_RENDERING_RESOURCE_PATH="$resource_root"
      break
    fi
  done
fi
