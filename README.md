# Lucy ROS 2 workspace (Humble)

Workspace bringup for the Lucy / InMoov humanoid. Everything (ROS 2 Humble, Gazebo, RViz, the web control panel) runs inside a single Docker container — you only need **Docker**, **Git** and **Python 3** on the host (plus **`xhost`** on Linux for GUI forwarding).

## Install

```bash
chmod +x install.sh launch_lucy.sh
./install.sh              # Linux, Intel Mac, Windows WSL, x86_64 VMs
./install.sh --arm        # Apple Silicon (M1 / M2 / M3) under Docker Desktop
```

`install.sh` clones the sub-repositories listed in `config/repos.json` into `src/`, builds the Docker image, and compiles the workspace inside the container.

## Launch

```bash
./launch_lucy.sh
```

Starts the **control panel** in the background and runs `lucy_bringup` with Gazebo and RViz inside the container (GUI / X11 forwarded automatically when available).

Open the control panel at **http://localhost:5000/**.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — developer guide: per-repo docs, all `install.sh` / `launch_lucy.sh` flags, dev mode, ports, environment overrides, packages overview.
