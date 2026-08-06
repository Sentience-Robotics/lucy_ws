# Lucy ROS 2 workspace (Humble)

Workspace bringup for the Lucy / InMoov humanoid. Everything (ROS 2 Humble, Gazebo, RViz, the web control panel) runs inside a single Docker container — you only need **Docker**, **Git** and **Python 3** on the host (plus **`xhost`** on Linux for GUI forwarding; on macOS the GUI is viewed over VNC with no extra software — see [GUI: RViz and Gazebo](#gui-rviz-and-gazebo)).

## Requirements

- [Python3](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/engine/install/)
- [Git](https://git-scm.com/downloads)

<sub>Linux GUI forwarding uses `xhost` (preinstalled). On Wayland run `xhost +local:docker` if windows don't open — see [GUI](#gui-rviz-and-gazebo).</sub>

> **Windows users:** see the [Windows README](windows/README.md) — **`Lucy-Setup.exe`** to install/update, **`Lucy.exe`** to launch.

## Get the repository

Install the [requirements](#requirements) first, then grab the repo. You can clone it with Git (recommended — makes updates a `git pull`) or download a ZIP.

**Option A — Clone with Git (recommended):**

```bash
git clone https://github.com/Sentience-Robotics/lucy_ws.git
```

**Option B — Download the ZIP:**

- Open the repository page on GitHub, click the green **Code** button, then **Download ZIP**, and extract it.

Then open a terminal and move into the project folder before running anything:

```bash
cd lucy_ws
```

> The manager (`Lucy.py`) must be run **from the repository root** — it reads `config/`, `Dockerfile.humble` and mounts the workspace relative to that directory.

## Quick start

A Python-based Text User Interface (TUI) manages the whole workspace — installing, rebuilding, and launching the environment. From the repository root, run the manager for your platform:

### Linux / macOS

```bash
python3 Lucy.py
```

> On UNIX systems, if you ever run the scripts by hand, `chmod +x install.sh launch_lucy.sh` first. `./install.sh` is only a fallback to `Lucy.py`.

### Windows

**Installer (recommended):** download `Lucy-Setup.exe` from [GitHub Releases](https://github.com/Sentience-Robotics/lucy_ws/releases), then see the [Windows README](windows/README.md).

**From source (developers):**

```bash
python windows/Lucy.py --cli install   # first time
python windows/Lucy.py                   # launch
```

> **Windows** additionally needs a third-party X Server for RViz/Gazebo — see the [Windows README](windows/README.md). End users should use **`Lucy-Setup.exe`** instead of manual install.

### Opening the Control Panel

After **`Launch`**, enable **Core + Control Panel** in the launcher. Once it is running, the **Lucy Control Panel is accessible in your browser at [http://localhost:3000](http://localhost:3000)** (or the next free port if 3000 is already taken). The launcher also shows the exact URL next to the Control Panel entry once it's up.


## Using the workspace

Selecting **Launch** from the manager starts everything inside a single **tmux** session in the Docker container. You first land on the **Lucy Control Center** TUI:

- **Up/Down arrows** — navigate
- **Space** — toggle a package or tool on/off
- **Enter** — apply your changes (new tools open in their own background windows)
- **X** — stop all processes and exit the container

### Launch options

What you toggle in the launcher falls into a few groups:

- **Core** — the base robot software stack (*lucy_bringup*), everything else builds on it.
- **Modifiers** (extend Core):
  - **Simulator (Gazebo)** — physics simulation
  - **Visualizer (RViz)** — ROS 3D visualizer
  - **Real Hardware** — connect to the physical robot
- **Interfaces:**
  - **Control Panel** — web UI with a built-in 3D viewer
  - **Lucy CLI** — terminal control interface
- **Tools** — Console, rqt, and VNC viewers.

Gazebo, RViz and rqt are native GUI apps and need a display — native X11 or the VNC desktop (see [GUI: RViz and Gazebo](#gui-rviz-and-gazebo)). Each interface/viewer that exposes a URL shows it right in the launcher once it's running.

> **Recommended starting point:** enable **Core + Control Panel**. The control panel's web 3D viewer is usually enough to get going and avoids the heavier GUI apps (Gazebo/RViz) entirely.

### Managing tmux windows

Tools (the console, CLI, viewers…) run in background windows, so a few `tmux` basics help you move between them:

- **`Ctrl+B` then `W`** — menu of all running windows; arrow to one and press Enter to switch.
- **`Ctrl+B` then `N`** — next window.
- **`Ctrl+B` then `P`** — previous window.

### Developer mode

The manager includes a **Developer Mode** toggle. When ON:
- repositories are pulled over SSH instead of HTTPS
- Core & the control panel aren't launched automatically
- the launch menu also shows **Headless mode** for Gazebo (no GUI / X11)

This setting is stored in a `.env` file.

## GUI: RViz and Gazebo

RViz, Gazebo and rqt are native OpenGL apps. The container can show them two ways:

- **Native X11** — Linux/amd64 hosts with a working GPU. Needs `xhost` on the host for display forwarding.
- **VNC virtual desktop** — a self-contained desktop inside the container: `Xvfb` rendered by
  Mesa `llvmpipe` (software OpenGL), a small window manager, and VNC + noVNC servers (see
  [`docker/gui_desktop.sh`](docker/gui_desktop.sh)). It is the default on Apple Silicon (arm64),
  where the container gets no native GL context, and can be enabled on any host on demand.

### Choosing VNC vs native X11 (`LUCY_FORCE_VNC`)

By default the mode is picked from your architecture. Set `LUCY_FORCE_VNC` in a root `.env`
(or the environment) to override — e.g. an amd64 Linux box can opt into the VNC desktop:

| `LUCY_FORCE_VNC` | Behaviour |
| :-- | :-- |
| unset *(default)* | Auto: VNC on arm64, native X11 on amd64 |
| `1` / `yes` / `true` | Force the VNC desktop on any architecture (e.g. an amd64 host without working GLX) |
| `0` / `no` / `false` | Force VNC off even on arm64 (fall back to native X11 / headless) |

### Connecting to the VNC desktop

Enable **noVNC** (browser) or the **VNC Server** (native clients) from the launcher, then open
the address it shows. Defaults:

| How | Address | Password |
| :-- | :-- | :-- |
| **Browser** (noVNC) | http://localhost:6080/vnc.html | (none) |
| **RealVNC Viewer** etc. | `localhost:5901` | `lucy` |
| macOS **Screen Sharing** | `open vnc://localhost:5901` | `lucy` |

- The launcher prints the real URL/port for each viewer once it's running; if a default port is
  already taken it automatically moves to the next free one.
- RealVNC Viewer warns the connection is unencrypted — expected over localhost; click through it.
- Override defaults with `LUCY_GUI_VNC_PORT` / `LUCY_GUI_NOVNC_PORT` (ports) and
  `LUCY_GUI_VNC_PASSWORD` (max 8 chars) in a root `.env`.

> **Software-rendered:** the VNC desktop has no GPU passthrough, so Gazebo runs but is CPU-slow.
> For heavy simulation prefer a native-X11 Linux host, or run headless
> (`./launch_lucy.sh --headless`) and visualize through the control panel.

### macOS notes

- On Apple Silicon, XQuartz can't give the container an OpenGL context, so the VNC desktop is
  used by default — no setup required.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — developer guide: per-repo docs, all `install.sh` / `launch_lucy.sh` flags, dev mode, ports, environment overrides, packages overview.
- [`docs/launcher_packages.md`](docs/launcher_packages.md) — launcher guide: how to add new packages to the launcher UI and understand the configuration fields.
