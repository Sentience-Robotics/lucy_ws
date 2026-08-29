# Lucy `lucy_ws` developer guide

ROS 2 **Jazzy** on Ubuntu 24.04 Noble. This document covers everything beyond the basic install/launch flow in the top-level [`README.md`](../README.md): per-repository docs, all install/launch flags, dev mode, ports, environment overrides, and an overview of the packages dropped under `src/`.

## Cross-repository docs

Maintainer documentation for each Lucy sub-repository is **owned per repository**:

| Repository | Developer documentation |
|------------|-------------------------|
| **lucy_ros_packages** | [`lucy_ros_packages/docs/DEVELOPER.md`](../src/lucy_ros_packages/docs/DEVELOPER.md) — bringup, `lucy_ros2_control`, `camera_ros`, CI; [**ros2_control on Lucy**](../src/lucy_ros_packages/doc/ROS2_CONTROL.md) |
| **inmoov_urdf** | [`inmoov_urdf/docs/DEVELOPER.md`](../src/inmoov_urdf/docs/DEVELOPER.md) — URDF/xacro, meshes, launches, RViz |

Repository-level READMEs: [`lucy_ros_packages`](../src/lucy_ros_packages/README.md), [`inmoov_urdf`](../src/inmoov_urdf/README.md).

## Packages dropped under `src/` by `install.sh`

- **inmoov_urdf** — InMoov URDF, RViz config, `control.launch.py`, `gazebo.launch.py`, `rviz_standalone.launch.py` (robot + viz; the web stack lives in `lucy_bringup`).
- **lucy_ros_packages** — `lucy_bringup`, `lucy_ros2_control`, `camera_ros`, etc.
- **lucy_control_panel** — Vite web app exposing the robot state and controls.

**Required** clones (core sim + panel stack): `inmoov_urdf`, `lucy_ros_packages`, `lucy_control_panel`.

**Optional** clones (not required for default bringup or CI smoke tests; needed for micro-ROS firmware bridges or audio hardware):

- **micro_ros_agent** — micro-ROS agent (`micro-ROS/micro-ROS-Agent`, branch `jazzy`). Marked `optional: true` in `repos.json`.
- **audio_common** — audio drivers (`ros-drivers/audio_common`, branch `ros2`). Marked `optional: true` in `repos.json`.

To skip optional repos, remove their entries from `config/repos.json.local` (or omit them when authoring a local override). `install.sh` still clones everything listed in the active repos config.

The exact set of repositories, branches and clone URLs is in [`config/repos.json`](../config/repos.json).

## `install.sh`

Pixi installs RoboStack Jazzy dependencies; `colcon build --symlink-install` builds the workspace; `yarn install` sets up the control panel.

`--symlink-install` keeps `install/share/<robot_package>/config/controllers.yaml` pointing at the **source tree** paths that `lucy_config_pipeline` writes (`src/inmoov_urdf/config/controllers.yaml`), so launch files and the pipeline stay aligned during iterative hardware edits.

Subsequent runs fast-forward each clone to the branch declared in `config/repos.json` and rebuild the workspace.

| Command | What it does |
|---------|--------------|
| `./install.sh` | Clone missing repos, pull existing ones, `pixi install`, colcon build |
| `./install.sh --repair` | Wipe each repo under `src/` then re-clone and rebuild |
| `./install.sh --build-only` | Skip git; `pixi install` + colcon + panel yarn |
| `./install.sh --skip-build` | Clone/pull only (CI) |

### Pixi multi-platform install

`pixi.toml` declares all workspace platforms (`linux-64`, `linux-aarch64`, `osx-arm64`, `osx-64`, `win-64`). Pixi solves each platform into a single committed **`pixi.lock`** ([Pixi multi-platform docs](https://pixi.prefix.dev/latest/workspace/multi_platform_configuration/), [RoboStack Getting Started](https://robostack.github.io/GettingStarted.html)).

- **`ros2-distro-mutex = "0.15.*"`** — keeps RoboStack packages on the same rebuild cycle ([RoboStack #125](https://github.com/RoboStack/ros-jazzy/issues/125)).
- **Platform-specific deps** use `[target.linux]`, `[target.unix]`, `[feature.ros.target.osx-*]` (not install-time exceptions).
- **`install.sh`** runs `pixi lock` once if `pixi.lock` is missing, then `pixi install`.
- **Pixi ≥ 0.78** recommended (`curl -fsSL https://pixi.sh/install.sh | bash`).

### RealSense (local build, not Pixi)

`ros-jazzy-realsense2-camera` is **not** in `pixi.toml`. Build locally when you need Intel RealSense hardware (`camera_ros` / MJPEG does not require this).

**When to run**

1. Complete a normal workspace build first (`./install.sh` or `pixi run build` + `panel-install`).
2. Then run RealSense locally — it is **not** part of the default colcon pass over `src/`.

```bash
./scripts/build_local_realsense.sh
```

`LUCY_BUILD_REALSENSE=1 ./install.sh` runs the same script **after** `pixi run build` and `panel-install`. It does not re-run a full workspace colcon build; it builds `librealsense` into `.local/realsense` and then colcon-builds `realsense2_camera` packages into the existing `install/` overlay.

**Paths and env**

- Default install prefix: `.local/realsense` (override with `LUCY_REALSENSE_PREFIX`).
- Clones and build trees: `.local/src`, `.local/build/realsense` (gitignored via `*.local` / `.local/`).
- Requires ROS env — run from `pixi shell` or after `install/setup.bash` exists (the script sources it when present).

**Platform notes**

- **Linux** — primary target; uses `nproc` for parallel librealsense compile.
- **macOS** — `nproc` is often missing; run from Linux or edit the script / pass a fixed `-j` if you build on macOS.
- **linux-aarch64** — common motivation for this path (RoboStack RealSense packages are unreliable there).

### SSH vs HTTPS clones (`DEV=true`)

`config/repos.json` carries both `url_https` (default) and `url_ssh` for each repo. To clone over SSH, copy `.env.example` to `.env` and set `DEV=true` before running `install.sh`. SSH keys must be configured for the relevant host.

### Local repo overrides (`config/repos.json.local`)

To point a repo at your own fork or a feature branch without editing the tracked `config/repos.json`, create **`config/repos.json.local`**. When present it is used instead of `repos.json` by both `install.sh` and the launcher (`windows/Lucy.py`), and it is gitignored so overrides are never committed.

Use the same structure as `repos.json` — list only the repos you want to override (or all of them). Each entry needs `name` (the folder under `src/`), `branch`, and both `url_https` and `url_ssh` (Developer Mode selects SSH, otherwise HTTPS):

```json
{
  "repos": [
    {
      "name": "inmoov_urdf",
      "branch": "my-feature-branch",
      "url_https": "https://github.com/your-user/inmoov_urdf.git",
      "url_ssh": "git@github.com:your-user/inmoov_urdf.git"
    }
  ]
}
```

Delete the file to fall back to the tracked `repos.json`.

### Local launcher overrides (`config/launcher_config.json.local`)

When present, **`config/launcher_config.json.local`** (gitignored) replaces [`config/launcher_config.json`](../config/launcher_config.json) for the Control Center package list.

Use **native workspace paths** and **simple Pixi commands** (e.g. `pixi run panel-dev` for the control panel). Do not use Docker-era `/workspace/...` paths or nested tmux `start`/`stop` objects unless you need a one-off — the launcher wraps panes in `pixi run` automatically.

For a multi-robot dev setup (InMoov + Thais), copy [`config/launcher_config.json.local.example`](../config/launcher_config.json.local.example) to `launcher_config.json.local` and edit branches/repos in `repos.json.local` as needed.

### Windows install profile (`config/install.profile.json`)

On Windows, **`Lucy-Setup.exe`** (or `Lucy.exe --cli …`) writes **`config/install.profile.json`** (gitignored) to record install choices: `lucy_ws` version, `repos_branch` (default `master`), `fetch_method` (`git` or `zip`), and whether **developer install** was selected. The file is created automatically on first install.

| Windows | Linux/macOS equivalent |
|---------|------------------------|
| `Lucy-Setup.exe` → Fresh install | `./install.sh` |
| `Lucy-Setup.exe` → Update | `./install.sh` / `./install.sh --update` |
| `Lucy-Setup.exe` → Repair | `./install.sh --repair` |
| `Lucy.exe` (no args) | `./launch_lucy.sh` / **Launch** in `Lucy.py` |
| `Lucy.exe --cli build-only` | `./install.sh --build-only` |

## `launch_lucy.sh`

Pixi activates the colcon overlay and starts the **Lucy Control Center** launcher. Default: a **tmux** session (`lucy_ws`) running `launcher.py`. GUI apps (Gazebo, RViz, rqt) use the **native host display** — no VNC desktop.

| Command | What it does |
|---------|--------------|
| `./launch_lucy.sh` | tmux + Control Center launcher |
| `./launch_lucy.sh --headless <cmd>` | Run one command headless (default: `ros2 doctor --report`) |
| `./launch_lucy.sh --shell` | Interactive `pixi shell` with typical `ros2 launch` hints |

On Windows, **`Lucy.exe`** runs `bash launch_lucy.sh` (Git Bash). Without tmux (Git Bash on Windows), it falls back to `pixi run -- python launcher.py`.

### TUI + Pixi CLI equivalence

| Action | Command |
|--------|---------|
| Install / update | `./install.sh` |
| Rebuild | `pixi run build` then `pixi run panel-install` |
| Launch | `./launch_lucy.sh` |
| Headless check | `./launch_lucy.sh --headless ros2 doctor --report` |
| Dev shell | `./launch_lucy.sh --shell` or `pixi shell` |
| Direct sim (optional) | `pixi run launch-sim` |
| Clean build dirs | `pixi run clean` |
| Workspace unit tests | `pixi run workspace-test` (launcher Pixi wrap, `repos.json` parsing) |

**Do not use `rosdep`** in this workspace — it bypasses Pixi/RoboStack. See [`docs/pixi_setup.md`](pixi_setup.md).

### `ros2 launch` cheat sheet (dev mode)

Run these inside the dev-mode shell — `lucy_bringup` already brings up `rosbridge` and the `/config/*` services via `web_ros_api`:

| What you want | Command |
|---------------|---------|
| Default Jetson stack (no RViz / no Gazebo) | `ros2 launch lucy_bringup lucy.launch.py real:=true` |
| Jetson + RViz | `ros2 launch lucy_bringup lucy.launch.py real:=true rviz:=true` |
| Dev + panel + RViz (no micro-ROS / cameras) | `ros2 launch lucy_bringup lucy.launch.py rviz:=true` |
| Gazebo sim + panel (`rviz:=false` = headless Gazebo) | `ros2 launch lucy_bringup lucy.launch.py gazebo:=true` |

`gazebo:=true` cannot be combined with `real:=true` (the launch aborts). With Gazebo, `rviz` maps to `start_rviz` in `inmoov_urdf/gazebo.launch.py`.

### SIMULATION ONLY + RELOAD (control panel)

From **Configuration → ACTIVATE**, enable **SIMULATION ONLY** to run **VALIDATE → ACTIVATE → RELOAD** without BUILD/FLASH. The pipeline generates a single mock `ros2_control` block and `lucy_sim_controller`, installs `inmoov_ros2_control.xacro` + `controllers.yaml` into the source robot tree, then calls **`/lucy_control/restart`** (`lucy_control_supervisor`) to restart `robot_state_publisher`, `ros2_control_node` (RViz-only), and controller spawners.

Hardware mode runs the same **RELOAD** step after BUILD/FLASH once ros2_control artifacts are regenerated.

**Gazebo caveat:** spawners and RSP can be restarted without relaunching the world; if you add/remove joints in the URDF hardware blocks, `gz_ros2_control` may require a full Gazebo restart — the supervisor response notes this when `use_gazebo_sim:=true`.

## Ports and environment overrides

| Env var | Default | Purpose |
|---------|---------|---------|
| `DEV` | unset | `true` → use `url_ssh` in `repos.json` during `install.sh` (SSH clones) |
| `PORT_CONTROL_PANEL` | next free port from container port | Host port published for the control panel URL |
| `PORT_CONTROL_PANEL_CONTAINER` | `VITE_PORT` from `src/lucy_control_panel/.env`, else `5000` | Port the Vite dev server listens on |
| `LUCY_LCP_PUBLISHED_HOST_PORT` | set by `launch_lucy.sh` | Host port embedded in launcher control-panel URLs |
| `LUCY_LCP_CONTAINER_PORT` | same as container Vite port | Internal Vite port for launcher URL templates |
| `LUCY_LCP_SCHEME` | `http` or `https` from `VITE_HTTPS` | Scheme for control panel URLs in the launcher |
| `PORT_ROSBRIDGE` | `9090` | rosbridge WebSocket port (optional `.env` override) |

Vite proxies `/rosbridge` to `ws://127.0.0.1:9090` inside the dev server. rosbridge listens on port `9090` by default.

## Pixi lock and dependencies

RoboStack packages are declared in [`pixi.toml`](../pixi.toml) and locked in **`pixi.lock`**. After changing dependencies, run `pixi install` to refresh the lock for all platforms in `pixi.toml`. Full workflow: [`docs/pixi_setup.md`](pixi_setup.md).
