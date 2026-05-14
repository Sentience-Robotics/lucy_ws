# Lucy ROS 2 workspace (Humble)

Workspace for Lucy/InMoov:

- **thais_urdf** (URDF + combo launches) — package name `thais_urdf`
- **lucy_ros_packages** (e.g. `lucy_ros2_control`, `lucy_bringup`, `camera_ros`)

This tree holds workspace layout and tooling; **`src/`** is populated by the install script.

## Install and quick launch

One-time:

```bash
chmod +x install.sh launch_lucy.sh
```

If you need to clone the repositories over **SSH**, copy **`.env.example`** to **`.env`** and set **`DEV=true`** before running **`install.sh`** (HTTPS clones work without that).

### Linux, Intel Mac, Windows WSL, x86_64 VMs

Docker pulls **`linux/amd64`** images — correct for these hosts.

**Install**

```bash
./install.sh
```

**Quick launch** (interactive shell; GUI / X11 if available)

```bash
./launch_lucy.sh
```

### Apple Silicon macOS (M1 / M2 / M3, Docker Desktop)

Docker Desktop often defaults to **`linux/amd64`** ROS images and runs them under emulation, which produces platform warnings and unreliable **`apt` / `rosdep`**. Use **`--arm`** on **install** once (or every install you want as ARM64); **`--arm`** can be combined with **`--build-only`**, **`--repair`**, etc. The image **`osrf/ros:humble-desktop`** on Docker Hub is **amd64-only**; **`--arm`** builds from **`ros:humble-ros-base-jammy`** and installs **`ros-humble-desktop`** so a real **linux/arm64** base exists.

**Install**

```bash
./install.sh --arm
```

**Quick launch** (same as on Linux — **`launch_lucy.sh`** reads **`.lucy-docker-platform`**)

```bash
./launch_lucy.sh
```

## Quick start (what happens in the container)

**launch_lucy.sh** builds the Docker image if needed, mounts the workspace, sources the built ROS overlay, and starts a shell (GUI by default). Run **`install.sh`** first so **`install/setup.bash`** exists.

An interactive run starts the **control panel** (**Vite**) **in the background** (log **`/tmp/lucy-control-panel-vite.log`**). Start **`lucy_bringup`** **`lucy.launch.py`** (defaults include **rosbridge** and **`/config/*`** via **`web_ros_api`**) before using the panel.

Inside the container:

| What you want | Command |
|---------------|---------|
| Default Jetson stack (no RViz / no Gazebo) | `ros2 launch lucy_bringup lucy.launch.py` |
| Jetson + RViz | `ros2 launch lucy_bringup lucy.launch.py rviz:=true` |
| Dev + panel + control + RViz (no micro-ROS / cameras) | `ros2 launch lucy_bringup lucy.launch.py real:=false rviz:=true` |
| Gazebo sim + panel (`rviz:=false` = headless Gazebo) | `ros2 launch lucy_bringup lucy.launch.py gazebo:=true real:=false` |

**Notes:** **`gazebo:=true`** requires **`real:=false`** (launch aborts otherwise). With Gazebo, **`rviz`** maps to **`start_rviz`** in **`thais_urdf/gazebo.launch.py`**.

**Control panel URL:** **`launch_lucy.sh`** reads **`src/lucy_control_panel/.env`** for **`VITE_PORT`** and publishes that host port into the container (defaults **5000** if **`VITE_PORT`** is missing). Override with **`PORT_CONTROL_PANEL`** / **`PORT_CONTROL_PANEL_CONTAINER`** if needed.

### More launch flags

```bash
./launch_lucy.sh --headless              # shell without GUI / X11
./launch_lucy.sh <command>               # one command; no background control panel
./launch_lucy.sh --headless ros2 doctor  # example non-interactive check
```

After **`./install.sh --arm`**, headless checks use the same **`./launch_lucy.sh`** flags (e.g. **`./launch_lucy.sh --headless ros2 doctor --report`**).

## Packages (`src/` after install)

- **thais_urdf** — InMoov URDF, RViz config, `control.launch.py`, `gazebo.launch.py`, `rviz_standalone.launch.py` (robot + viz; web stack lives in **lucy_bringup**)
- **lucy_ros_packages** — bringup, `lucy_ros2_control`, `camera_ros`, etc.

See each repository’s README for details.

## Other install commands

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

On Apple Silicon, add **`--arm`** to any of the above **`install.sh`** invocations (e.g. **`./install.sh --arm --build-only`**).