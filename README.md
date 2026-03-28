# Lucy ROS 2 workspace (Humble)

Workspace for Lucy/InMoov:

- **thais_urdf** (URDF + combo launches) — package name `thais_urdf`
- **lucy_ros_packages** (e.g. `lucy_ros2_control`, `lucy_bringup`, `camera_ros`)

This tree holds workspace layout and tooling; **`src/`** is populated by the install script.

## Building the workspace

**First-time setup:** **install.sh** checks requirements (Docker, git, python3), reads **config/repos.json**, clones each listed repo into **src/**, runs **launch_lucy.sh --install** to build the workspace in Docker, then exits.

```bash
chmod +x install.sh launch_lucy.sh
./install.sh
```

If all repos are already cloned, the script asks whether to repair (re-clone and rebuild) or abort.

**Rebuild only** (no full install flow):

```bash
./launch_lucy.sh --install
```

## Quick start

**launch_lucy.sh** builds the Docker image if needed, mounts the workspace, runs colcon in the container, and starts a shell (GUI by default).

```bash
./launch_lucy.sh
```

Inside the container:

| What you want | Command |
|---------------|---------|
| Real robot + RViz + rosbridge | `ros2 launch thais_urdf rviz.launch.py` |
| Real robot, control only | `ros2 launch lucy_ros2_control control.launch.py` |
| Gazebo sim + RViz + rosbridge | `ros2 launch thais_urdf gazebo.launch.py` |

### Launch script options

```bash
./launch_lucy.sh --headless   # shell without GUI
./launch_lucy.sh --install    # build workspace only and exit
./launch_lucy.sh <command>    # run one command in the container
```

When using GUI, the script runs `xhost +local:docker` if available so the container can use the host display.

## Packages (`src/` after install)

- **thais_urdf** — InMoov URDF, RViz config, `rviz.launch.py`, `gazebo.launch.py`
- **lucy_ros_packages** — bringup, `lucy_ros2_control`, `camera_ros`, etc.

See each repository’s README for details.
