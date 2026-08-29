# Lucy ROS 2 workspace (Jazzy)

Workspace bringup for the Lucy / InMoov humanoid. ROS 2 Jazzy, Gazebo, RViz, and the web control panel run **natively** via [Pixi](https://pixi.prefix.dev/) and [RoboStack](https://robostack.github.io/) — no Docker required for day-to-day development.

## Requirements

- [Git](https://git-scm.com/downloads)
- [Python 3](https://www.python.org/downloads/) (for `Lucy.py`)
- [Pixi](https://pixi.prefix.dev/latest/installation/) **≥ 0.78** — or use the Nix flake below on NixOS

<sub>Linux GUI apps (RViz, Gazebo, rqt) use your native display. On Wayland you may need `xhost +local:` or run under X11 — see [GUI: RViz and Gazebo](#gui-rviz-and-gazebo).</sub>

> **Windows users:** see the [Windows README](windows/README.md) — **`Lucy-Setup.exe`** to install/update, **`Lucy.exe`** to launch.

## Developer install (Linux)

Host tools only — ROS packages are installed by Pixi into `.pixi/`.

### Ubuntu / Debian and other distros

Install Pixi, then from the repository root:

```bash
curl -fsSL https://pixi.sh/install.sh | bash   # or see pixi.prefix.dev
./install.sh
```

Optional: `chmod +x install.sh launch_lucy.sh` if you run scripts directly.

### NixOS

On NixOS, install **host tools from nixpkgs** (pixi, git, python3, tmux) inside an FHS dev shell. RoboStack binaries still come from Pixi.

**Prerequisites:** Flakes enabled (`nix-command` + `flakes` in `nix.settings.experimental-features`, or:

```bash
export NIX_CONFIG="experimental-features = nix-command flakes"
```

**Recommended workflow** — enter the dev shell, then install:

```bash
cd lucy_ws
nix develop
./install.sh
```

The repo includes [`flake.nix`](flake.nix) with `buildFHSEnv` so Pixi and conda/RoboStack have a conventional Linux filesystem layout (glibc, etc.).

**One-shot** (FHS wrapper, no interactive shell):

```bash
nix run .#install
```

**Without the flake** — install Pixi globally and run `./install.sh` from any shell:

```bash
nix profile install nixpkgs#pixi
# or: nix-shell -p pixi git python3 tmux --run ./install.sh
```

After the first `pixi install`, you can also use `pixi shell` for a ROS-enabled environment without `nix develop`.

## Get the repository

**Option A — Clone with Git (recommended):**

```bash
git clone https://github.com/Sentience-Robotics/lucy_ws.git
cd lucy_ws
```

**Option B — Download the ZIP** from GitHub (**Code → Download ZIP**), then extract and `cd lucy_ws`.

> The manager (`Lucy.py`) must be run **from the repository root** — it reads `config/` and paths relative to that directory.

## Quick start

A Python TUI manages install, rebuild, and launch. From the repository root:

### Linux / macOS

```bash
python3 Lucy.py
```

> `./install.sh` and `./launch_lucy.sh` are CLI equivalents when you prefer not to use the TUI.

### Windows

**Installer (recommended):** download `Lucy-Setup.exe` from [GitHub Releases](https://github.com/Sentience-Robotics/lucy_ws/releases), then see the [Windows README](windows/README.md).

**From source (developers):**

```bash
python windows/Lucy.py --cli install   # first time
python windows/Lucy.py                   # launch
```

### Opening the Control Panel

After **Launch**, enable **Core + Control Panel** in the launcher. The **Lucy Control Panel** is at [http://localhost:5000](http://localhost:5000) (or **5001** if 5000 is taken — common on macOS with AirPlay). The launcher shows the exact URL once the panel is up.

## Using the workspace

**Launch** starts a **tmux** session and the **Lucy Control Center** TUI:

- **Up/Down** — navigate
- **Space** — toggle a package or tool
- **Enter** — apply changes
- **X** — stop all processes and exit

### Launch options

- **Core** — base robot stack (`lucy_bringup`)
- **Modifiers:** Simulator (Gazebo), Visualizer (RViz), Real Hardware
- **Interfaces:** Control Panel (web UI), Lucy CLI
- **Tools:** Console, rqt

Gazebo, RViz, and rqt are native GUI apps on your host display. Each URL-based interface shows its address in the launcher when running.

> **Recommended starting point:** **Core + Control Panel** — the web 3D viewer is enough for most work without heavy GUI apps.

### Managing tmux windows

- **`Ctrl+B` then `W`** — window list
- **`Ctrl+B` then `N`** / **`P`** — next / previous window

### Developer mode

With **Developer Mode** ON in the TUI (stored in `.env`):

- repos are pulled over SSH instead of HTTPS
- Core and the control panel are not auto-launched
- **Headless mode** appears for Gazebo

### CLI equivalents

| TUI action | Command |
|------------|---------|
| Install | `./install.sh` |
| Rebuild | `pixi run build` then `pixi run panel-install` |
| Launch | `./launch_lucy.sh` |
| Headless | `./launch_lucy.sh --headless` |

## GUI: RViz and Gazebo

RViz, Gazebo, and rqt are native OpenGL applications. They use your **host display** (`DISPLAY` / Wayland compositor). No in-container VNC desktop.

- **Linux (amd64)** — GPU acceleration when drivers and GLX/EGL are available
- **Apple Silicon** — native display; performance depends on host GL stack
- **Headless simulation** — `./launch_lucy.sh --headless` or enable Headless in the launcher; visualize via the control panel

### macOS notes

- **Port 5000** may be used by AirPlay Receiver. Disable it in **System Settings → General → AirDrop & Handoff**, or set `PORT_CONTROL_PANEL=5001` in `.env`.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — install/launch flags, dev mode, ports, packages overview
- [`docs/launcher_packages.md`](docs/launcher_packages.md) — launcher configuration
- [`docs/pixi_setup.md`](docs/pixi_setup.md) — Pixi/RoboStack dependency and lock workflow
