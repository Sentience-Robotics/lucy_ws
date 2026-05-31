# Lucy ROS 2 workspace (Humble)

Workspace bringup for the Lucy / InMoov humanoid. Everything (ROS 2 Humble, Gazebo, RViz, the web control panel) runs inside a single Docker container — you only need **Docker**, **Git** and **Python 3** on the host (plus **`xhost`** on Linux for GUI forwarding).

## Requirements

- Python3
- Docker

## Install

> For UNIX based system:
```bash
chmod +x install.sh launch_lucy.sh
```

The installation is handled by the `Lucy.py` script. Only use the `./install.sh` script as a fallback.

## Launch & Manage

We provide a Python-based Text User Interface (TUI) to easily manage the workspace. It handles installing, rebuilding, and launching the environment.

From the repository root, run the manager for your platform:

| OS | Command                                                            |
| :--- |:-------------------------------------------------------------------|
| **Linux / macOS** | `python3 Lucy.py`                                                  |
| **Windows** | `python windows/Lucy.py` (See [Windows README](windows/README.md)) |

> The windows installation require the installation of a 3rd party software, as a Windows X Server is needed.

### Developer mode

The manager includes a **Developer Mode** toggle. When ON: 
- repositories are pulled using SSH instead of HTTP
- The core & control panel aren't launch automatically

This setting is stored in a .env file

### Using the Workspace

Selecting **Launch** from the manager starts the workspace, running everything inside a single **tmux** session within the Docker container. 

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
