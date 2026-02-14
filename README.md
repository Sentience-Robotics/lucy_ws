# Lucy ROS 2 workspace (Humble)

Workspace for Lucy/InMoov:
- **inmoov_urdf** (URDF + combo launches)
- **lucy_ros2_control** (real-only control + hardware interface)
This repo contains only the workspace layout and launch tooling; **src/** is filled by the install script.

## Install script (first-time setup)

**install.sh** checks requirements (docker, git, python3), reads **config/repos.json**, clones each listed repo (name, branch, url) into **src/**, runs **launch_lucy.sh --install** to build the workspace in Docker, then exits.

Run from the workspace root:
   ```bash
   chmod +x install.sh launch_lucy.sh
   ./install.sh
   ```

If all repos in the config are already cloned, the script will ask whether to repair (re-clone and re-build) or abort. To only rebuild, run **launch_lucy.sh --install**, then **launch_lucy.sh** to start a shell.

## Launch script (after install)

**launch_lucy.sh** builds the Docker image if needed, mounts the workspace, builds with colcon, and starts a shell (GUI by default). When run with GUI, it runs `xhost +local:docker` if available so the container can use the host display.

```bash
./launch_lucy.sh              # interactive shell with X11 (RViz2/Gazebo)
```

Inside the container:

| What you want | Command |
|---------------|--------|
| Real robot + RViz + rosbridge | `ros2 launch thais_urdf rviz.launch.py` |
| Real robot, control only | `ros2 launch lucy_ros2_control control.launch.py` |
| Gazebo sim + RViz + rosbridge | `ros2 launch thais_urdf gazebo.launch.py` |

### Advanced usage

```bash
./launch_lucy.sh --headless   # shell without GUI
./launch_lucy.sh --install    # build workspace only and exit
./launch_lucy.sh <command>    # run one command in the container
```

## Packages (in src/ after install)

- **inmoov_urdf** — InMoov URDF, RViz config, `rviz.launch.py`, `gazebo.launch.py`.
- **lucy_ros2_control** — ros2_control hardware interface, controller config, `control.launch.py`.

See each package’s README for details.
