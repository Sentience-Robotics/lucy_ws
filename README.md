# Lucy ROS 2 workspace (Humble)

Workspace bringup for the Lucy / InMoov humanoid. Everything (ROS 2 Humble, Gazebo, RViz, the web control panel) runs inside a single Docker container — you only need **Docker**, **Git** and **Python 3** on the host (plus **`xhost`** on Linux for GUI forwarding; on macOS the GUI is viewed over VNC with no extra software — see [GUI on macOS](#gui-on-macos)).

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
- the launch menu also shows **Headless mode for Gazebo** without GUI / X11

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

## GUI on macOS

On Apple Silicon, XQuartz cannot give the container an OpenGL.

Instead, `launch_lucy.sh` runs a **self-contained virtual desktop inside the
container** — `Xvfb` rendered by Mesa `llvmpipe` (software OpenGL), a small window manager,
and a VNC + noVNC server (see [`docker/gui_desktop.sh`](docker/gui_desktop.sh)). RViz/Gazebo
render there and you view the desktop from your Mac. This is automatic; there is no setup.

**View RViz/Gazebo** after launching (Core + Simulator/Visualizer).

> NoVNC in the browser has no password
> On RealVNC Viewer and other VNC clients, the VNC server is password-protected (default **`lucy`**).

| How | Address | Password |
| :-- | :-- | :-- |
| **Browser** (noVNC) | http://localhost:6080/vnc.html | (none) |
| **RealVNC Viewer** etc. | `localhost:5901` | `lucy` |
| macOS **Screen Sharing** | `open vnc://localhost:5901` | `lucy` |

- RealVNC Viewer warns the connection is unencrypted — that's expected over localhost;
  click through it.
- Override with `LUCY_GUI_VNC_PORT` / `LUCY_GUI_NOVNC_PORT` (ports) and
  `LUCY_GUI_VNC_PASSWORD` (max 8 chars) in a root `.env`.

> **Software-rendered:** there is no GPU passthrough, so Gazebo runs but is CPU-slow. For
> heavy simulation prefer a Linux host, or run headless (`./launch_lucy.sh --headless`) and
> visualize through the web control panel.

**Port 5000** is taken by macOS AirPlay Receiver. The control panel defaults there, so
either disable **System Settings → General → AirDrop & Handoff → AirPlay Receiver**, or set
`PORT_CONTROL_PANEL=5001` in a root `.env`.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — developer guide: per-repo docs, all `install.sh` / `launch_lucy.sh` flags, dev mode, ports, environment overrides, packages overview.
- [`docs/launcher_packages.md`](docs/launcher_packages.md) — launcher guide: how to add new packages to the launcher UI and understand the configuration fields.
