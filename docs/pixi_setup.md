# Pixi + RoboStack setup

Lucy uses [Pixi](https://pixi.prefix.dev/) with the [RoboStack Jazzy](https://robostack.github.io/) channel for ROS 2 Jazzy dependencies. Workspace packages under `src/` are built with **colcon** into `install/`; Pixi provides the base ROS environment and activation scripts.

## Do not use rosdep

**Do not run `rosdep install`** in this workspace. rosdep resolves system packages via apt and bypasses Pixi, which breaks the reproducible RoboStack environment.

Instead:

- Add missing ROS packages with `pixi add --feature ros ros-jazzy-<package>` (or edit `[feature.ros.dependencies]` in `pixi.toml`).
- Clone packages that are not on RoboStack into `src/` via [`config/repos.json`](../config/repos.json).

## Dependency audit workflow

When adding or changing workspace packages:

1. Read `package.xml` / `CMakeLists.txt` for new `depend` / `find_package` entries.
2. Check whether RoboStack provides `ros-jazzy-<name>` on [prefix.dev/robostack-jazzy](https://prefix.dev/robostack-jazzy).
3. If available, add to `pixi.toml` under `[feature.ros.dependencies]`.
4. If not available (e.g. `micro_ros_agent`, `audio_common`, custom forks), add a clone entry to `config/repos.json`.
5. Regenerate the lock and install:

```bash
pixi install          # updates pixi.lock for every platform in pixi.toml
```

`install.sh` runs `pixi lock` automatically if `pixi.lock` is missing, then `pixi install`.

**Pixi ≥ 0.78** is recommended for multi-platform lock resolution (`curl -fsSL https://pixi.sh/install.sh | bash`).

## RoboStack vs source clones

| Approach | When to use |
|----------|-------------|
| **Pixi / RoboStack** | Standard ROS Jazzy packages (`ros-jazzy-desktop`, `ros-jazzy-ros-gz`, controllers, rosbridge, etc.) |
| **Clone to `src/`** | Packages not on RoboStack, forks, or workspace-specific repos (`lucy_ros_packages`, `inmoov_urdf`, `micro_ros_agent`, `audio_common`) |
| **Local build** | RealSense — not in Pixi; use `./scripts/build_local_realsense.sh` or `LUCY_BUILD_REALSENSE=1 ./install.sh` |

### Mutex pin

`ros2-distro-mutex = "0.15.*"` in `pixi.toml` keeps all RoboStack packages on the same rebuild cycle ([RoboStack #125](https://github.com/RoboStack/ros-jazzy/issues/125)).

### Platform-specific deps

Use Pixi target tables in `pixi.toml`:

- `[target.linux]` — `gstreamer`, `libgl-devel`
- **tmux** — host package (apt, Homebrew); not in Pixi
- `[feature.ros.target.osx-*]` — `pygraphviz`, Cyclone DDS RMW

## Build and activation

| Task | Command |
|------|---------|
| Install env | `pixi install` |
| Build workspace | `pixi run build` |
| Control panel deps | `pixi run panel-install` |
| Tests | `pixi run test` |
| ROS doctor | `pixi run doctor` |
| Interactive shell | `pixi shell` |

Colcon uses `--symlink-install` on Linux/macOS and `--merge-install` on Windows (`pixi.toml` `[feature.build]` tasks).

Activation scripts (`install/setup.bash` or `install/setup.bat`) are wired via `[target.unix.activation]` / `[target.win.activation]` in `pixi.toml`, so `pixi run` and `pixi shell` automatically overlay the workspace.

## Lock refresh checklist

After editing `pixi.toml`:

```bash
pixi install
git add pixi.toml pixi.lock
```

Commit both files together so CI and other platforms stay in sync.

## Release builds (follow-up)

End-user **pre-built** packages via `pixi-build-ros` and conda channels are planned as a separate release workflow. See [`docs/pixi_release.md`](pixi_release.md).
