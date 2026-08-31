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

The exact set of repositories, branches and clone URLs is in [`config/repos.json`](../config/repos.json).

## `install.sh`

The first run clones missing sub-repositories, builds the Docker image (`lucy_ros2:jazzy`), and runs `rosdep` + `colcon build --symlink-install` + `yarn install` inside the container.

`--symlink-install` keeps `install/share/<robot_package>/config/controllers.yaml` pointing at the **source tree** paths that `lucy_config_pipeline` writes (`src/inmoov_urdf/config/controllers.yaml`), so launch files and the pipeline stay aligned during iterative hardware edits.

Subsequent runs fast-forward each clone to the branch declared in `config/repos.json` and rebuild the workspace.

| Command | What it does |
|---------|--------------|
| `./install.sh` | Clone missing repos, pull existing ones, rebuild the workspace |
| `./install.sh --repair` | Wipe each repo under `src/` then re-clone and rebuild |
| `./install.sh --build-only` | Skip git; just rebuild the workspace inside the container |
| `./install.sh --arm[...]` | Build / run the image as `linux/arm64` (Apple Silicon under Docker Desktop). Persists in `.lucy-docker-platform`; combine with any other flag |

### Apple Silicon notes

Docker Desktop on Apple Silicon defaults to `linux/amd64` when no platform is pinned, which runs the container under emulation and can make `apt` / `rosdep` unreliable. Use `./install.sh --arm` to build and run a native `linux/arm64` image on `ubuntu:24.04` with `ros-jazzy-*` packages from apt (recorded in `.lucy-docker-platform`).

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

Builds the Docker image if needed, mounts the workspace at `/workspace`, sources the built ROS overlay, then:

- **Normal mode (default)** — starts the control panel (Vite) in the background and runs `ros2 launch lucy_bringup lucy.launch.py gazebo:=true rviz:=true` in the foreground. GUI / X11 forwarded automatically when available.
- **Dev mode (`DEV=true` in env or `.env`)** — same control panel in the background, but drops you into an interactive Jazzy shell so you can run any `ros2 launch` yourself (the script prints typical commands).

| Command | What it does |
|---------|--------------|
| `./launch_lucy.sh` | Default launch (Control Panel + RViz + Gazebo, or dev shell when `DEV=true`) |
| `./launch_lucy.sh --headless` | Same flow without GUI / X11 (Gazebo runs headless, RViz is disabled) |
| `./launch_lucy.sh <command>` | Run a single command in the container — no control panel, no auto-launch |
| `DEV=true ./launch_lucy.sh` | Force dev mode for one run |

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
| `DEV` | unset | `true` → use `url_ssh` in `repos.json` (install) and the interactive dev shell (launch) |
| `PORT_CONTROL_PANEL` | matches container port | Host port the control panel is published on |
| `PORT_CONTROL_PANEL_CONTAINER` | `VITE_PORT` from `src/lucy_control_panel/.env`, else `4004` | Port the Vite dev server listens on inside the container |
| `DOCKER_GUI_DISPLAY` | host `$DISPLAY` | X display string passed to the container (use when the host `DISPLAY` doesn't reach Docker, e.g. Docker Desktop) |
| `DOCKER_GUI_USE_HOST_NETWORK` | unset | Run with `--network=host` and `DISPLAY=:0` (alternative GUI path) |
| `LUCY_DOCKER_PLATFORM` | content of `.lucy-docker-platform`, else host CPU | Docker `--platform` to build/run with (e.g. `linux/arm64`) |
| `LUCY_INSTALL_SKIP_XHOST` | unset | Skip the `xhost` requirement in `install.sh` (set automatically when `CI=true`) |

Inside the container, Vite proxies `/rosbridge` to `ws://127.0.0.1:9090`, and rosbridge is published on host port `9090`.

## Docker image rebuilds

`docker/ensure_image.sh` stamps each built image with `LABEL lucy.dockerfile.sha256="<sha256>|<platform>"`. Both `install.sh` and `launch_lucy.sh` rebuild the image when the label no longer matches the current `Dockerfile.jazzy` + target platform.
