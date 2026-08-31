# Lucy ROS 2 workspace (Jazzy)

Workspace bringup for the Lucy / InMoov humanoid. ROS 2 Jazzy, Gazebo, RViz, and the web control panel run **natively** via [Pixi](https://pixi.prefix.dev/) and [RoboStack](https://robostack.github.io/) — no Docker required for day-to-day development.

## Requirements

| Requirement | Linux | macOS | Windows |
|-------------|-------|-------|---------|
| [Git](https://git-scm.com/downloads) | ✓ | ✓ | ✓ ([Git for Windows](https://git-scm.com/install/windows)) |
| [Python 3](https://www.python.org/downloads/) (for `Lucy.py`) | ✓ | ✓ | ✓ |
| [Pixi](https://pixi.prefix.dev/latest/installation/) **≥ 0.78** | ✓ | ✓ | ✓ |
| **tmux** (multi-window launcher) | ✓ | ✓ (`brew install tmux`) | — (launcher runs directly) |

ROS packages are installed by Pixi into `.pixi/`; you do not need a system ROS install.

GUI apps (RViz, Gazebo, rqt) use your **native display**. Platform-specific notes (Wayland, AirPlay port conflicts) are in the [developer guide](docs/developer_lucy_packages.md#platform-setup).

## Get the repository

**Clone (recommended):**

```bash
git clone https://github.com/Sentience-Robotics/lucy_ws.git
cd lucy_ws
```

**Or** download the ZIP from GitHub (**Code → Download ZIP**), extract, and `cd lucy_ws`.

Run `Lucy.py` and the install scripts **from the repository root** — they read `config/` and paths relative to that directory.

## Install

### Linux / macOS

```bash
curl -fsSL https://pixi.sh/install.sh | bash   # if Pixi is not installed
export PATH="$HOME/.pixi/bin:$PATH"            # if needed
./install.sh
```

### Windows

**End users:** download **`Lucy-Setup.exe`** from [GitHub Releases](https://github.com/Sentience-Robotics/lucy_ws/releases). It installs Lucy, clones sub-repos, runs `pixi install`, and builds the workspace. See the [Windows README](windows/README.md).

**Developers (from source):**

```powershell
python windows\Lucy.py --cli install --repos-branch master
```

Or from Git Bash: `./install.sh`

## Quick start

After install, launch the **Lucy manager** TUI from the repository root.

### Linux / macOS

```bash
python3 Lucy.py
```

### Windows

**End users:** open **Lucy** from the Start Menu (runs `Lucy.exe` → Control Center).

**Developers:**

```powershell
python windows\Lucy.py
```

Or Git Bash: `./launch_lucy.sh`

## Using the Lucy launcher

After **`Launch`**, enable **Core + Control Panel** in the launcher. Once it is running, the **Lucy Control Panel is accessible in your browser at [http://localhost:4004](http://localhost:4004)** (or the next free port if 4004 is already taken). The launcher also shows the exact URL next to the Control Panel entry once it's up.

| Key | Action |
|-----|--------|
| **Up/Down** | Navigate |
| **Space** | Toggle a package or tool |
| **Enter** | Apply changes / Start / Restart |
| **X** | Stop all processes and exit |

**Components you can enable:**

- **Core** — base robot stack (`lucy_bringup`)
- **Modifiers** — Simulator (Gazebo), **… headless** (server-only sim, under Simulator), Visualizer (RViz), Real Hardware
- **Interfaces** — Control Panel (web UI), Lucy CLI
- **Tools** — Console, rqt

> **Recommended starting point:** **Core + Control Panel** — the web 3D viewer is enough for most work without heavy GUI apps.

**Control panel:** after Launch, enable **Core + Control Panel**. Open [http://localhost:5000](http://localhost:5000) (or the URL shown in the launcher if another port was chosen).

**tmux windows** (Linux/macOS):

- **`Ctrl+B` then `W`** — window list
- **`Ctrl+B` then `N`** / **`P`** — next / previous window

On Windows, the Control Center runs without tmux (one process tree). Gazebo, RViz, and rqt still open as native GUI apps when enabled.

## Developer setup

<<<<<<< HEAD
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
=======
For developer mode, Pixi component tasks (`pixi run core`, `sim-headless`, …), debug shell, SSH clones, local repo overrides, ports, and advanced launch options, see the **[developer guide](docs/developer_lucy_packages.md)**.
>>>>>>> 41e84e8 (evol(windows,docs): update Windows support and documentation)
