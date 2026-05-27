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

Starts the workspace, running everything inside a single **tmux** session in the Docker container. 

You will immediately see the **Lucy Control Center** TUI:
- Use **Up/Down Arrows** to navigate.
- Press **Space** to toggle a package or tool on/off.
- Press **Enter** to apply your changes. (New tools open in their own background windows).
- Press **X** to stop all processes and exit the Docker container entirely.

### Managing Tmux Windows

Because all tools (like the console or the control panel) run in background windows, you need to know a few basic `tmux` commands to navigate between them:

- **`Ctrl+B` then `W`**: Opens a menu of all running windows. Use the arrows to select one and press Enter to switch to it.
- **`Ctrl+B` then `N`**: Go to the next window.
- **`Ctrl+B` then `P`**: Go to the previous window.
- **`Ctrl+B` then `D`**: Detach from the session (keeps the container running in the background).

Open the control panel at **http://localhost:5000/**.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — developer guide: per-repo docs, all `install.sh` / `launch_lucy.sh` flags, dev mode, ports, environment overrides, packages overview.
- [`docs/launcher_packages.md`](docs/launcher_packages.md) — launcher guide: how to add new packages to the launcher UI and understand the configuration fields.
