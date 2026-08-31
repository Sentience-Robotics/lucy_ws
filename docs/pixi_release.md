# Pixi release infrastructure (follow-up PR)

This document outlines the **deferred** end-user release path. The PoC branch keeps day-to-day development on **colcon + Pixi activation**; release packaging is a separate PR after validation gates are green.

## Scope

Full-stack artifact (not `lucy_bringup` alone):

- All `lucy_ros_packages/*`, `inmoov_urdf`, optional `thais_urdf`
- External clones built in CI (`micro_ros_agent`)
- Launcher assets + control panel packaging strategy
- Release CI manifest with `preview = ["pixi-build"]` only in the release workflow

## Distribution options

| Option | Best for |
|--------|----------|
| Private conda channel (prefix.dev) | Networked workstations |
| Pixi Pack bundles | Jetson / air-gapped |

## Suggested follow-up commits

1. `chore(pixi): add per-package pixi.toml stubs for release builds`
2. `ci(release): add tag-triggered workflow with pixi-build-ros`
3. `docs(pixi): document end-user install from channel or Pixi Pack`

## References

- [pixi-build-ros](https://github.com/RoboStack/pixi-build-ros)
- Dev workflow: [`docs/pixi_setup.md`](pixi_setup.md)
