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

**NixOS:** enable [nix-ld](https://github.com/nix-community/nix-ld) so Pixi/RoboStack conda binaries can load the host dynamic linker (required before `./install.sh`):

```nix
programs.nix-ld.enable = true;
```

For Gazebo/RViz GL, also see the [NixOS notes](docs/developer_lucy_packages.md#platform-setup) in the developer guide.

### Windows

Install [Pixi](https://pixi.prefix.dev/latest/installation/) **≥ 0.78** first, then close and reopen your terminal so `PATH` is updated.

**PowerShell (recommended):**

```powershell
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

Alternatives from the [Pixi installation guide](https://pixi.prefix.dev/latest/installation/): `winget install prefix-dev.pixi`, Scoop, or the MSI from GitHub Releases.

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

**Launch** starts a **tmux** session (Linux/macOS) and the **Lucy Control Center** TUI (`python -m launcher`, or `python launcher.py` / `./launch_lucy.sh`):

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

**Control panel:** after Launch, enable **Core + Control Panel**. Open [http://localhost:4004](http://localhost:4004) (or the URL shown in the launcher if another port was chosen).

**tmux windows** (Linux/macOS):

- **`Ctrl+B` then `W`** — window list
- **`Ctrl+B` then `N`** / **`P`** — next / previous window

On Windows, the Control Center runs without tmux (one process tree). Gazebo, RViz, and rqt still open as native GUI apps when enabled.

## Developer setup

For developer mode, Pixi component tasks (`pixi run core`, `sim-headless`, …), debug shell, SSH clones, local repo overrides, ports, and advanced launch options, see the **[developer guide](docs/developer_lucy_packages.md)**.

## More

- [`docs/developer_lucy_packages.md`](docs/developer_lucy_packages.md) — developer guide: per-repo docs, all `install.sh` / `launch_lucy.sh` flags, dev mode, ports, environment overrides, packages overview.
- [`docs/launcher_packages.md`](docs/launcher_packages.md) — launcher guide: how to add new packages to the launcher UI and understand the configuration fields.
