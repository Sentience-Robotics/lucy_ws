# Lucy ROS 2 workspace (Humble)

Workspace for Lucy/InMoov:

- **thais_urdf** (URDF + combo launches) — package name `thais_urdf`
- **lucy_ros_packages** (e.g. `lucy_ros2_control`, `lucy_bringup`, `camera_ros`)

This tree holds workspace layout and tooling; **`src/`** is populated by the install script.

## Building the workspace

If you want to clone over ssh (for development purposes for example), copy `.env.example` to `.env` to use the env var `DEV=true` before running the install script.
Else, just run:

```bash
chmod +x install.sh launch_lucy.sh
./install.sh
```

If repos are already cloned, a normal **`./install.sh`** run **pulls** each repo to the branch in **config/repos.json** (fast-forward only), then rebuilds in Docker.

```bash
./install.sh --update     # same behavior (explicit “update”)
./install.sh update
```

**Force re-clone** everything listed in **repos.json** (removes **`src/<repo>`**, then clone + Docker build):

```bash
./install.sh --repair
```

**Rebuild only** (no git; Docker **rosdep** / **colcon** / **yarn** only):

```bash
./install.sh --build-only
```

## Quick start

**launch_lucy.sh** builds the Docker image if needed, mounts the workspace, sources the built ROS overlay, and starts a shell (GUI by default). Run **install.sh** first so **install/setup.bash** exists.

An interactive run starts the **control panel** (**Vite**) **in the background** (log **`/tmp/lucy-control-panel-vite.log`**). Start **Gazebo** or **RViz** yourself so **rosbridge** is running before using the panel.

**Control panel URL:** **`launch_lucy.sh`** reads **`src/lucy_control_panel/.env`** for **`VITE_PORT`** and publishes that host port into the container (defaults **5000** if **`VITE_PORT`** is missing). Override with **`PORT_CONTROL_PANEL`** / **`PORT_CONTROL_PANEL_CONTAINER`** if needed.

```bash
./launch_lucy.sh
```

Inside the container:

| What you want | Command |
|---------------|---------|
| Gazebo + RViz + Control Panel | `ros2 launch thais_urdf gazebo.launch.py` |
| RViz + Control Panel | `ros2 launch thais_urdf rviz.launch.py` |
| Real robot, control only | `ros2 launch lucy_ros2_control control.launch.py` |

### Launch script options

```bash
./launch_lucy.sh --headless   # shell without GUI
./launch_lucy.sh <command>    # run one command in the container (no background control panel)
```

## Packages (`src/` after install)

- **thais_urdf** — InMoov URDF, RViz config, `rviz.launch.py`, `gazebo.launch.py`
- **lucy_ros_packages** — bringup, `lucy_ros2_control`, `camera_ros`, etc.

See each repository’s README for details.
