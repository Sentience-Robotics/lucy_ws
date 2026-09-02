# Windows launcher and installer

On Windows, Lucy is split into two programs:

| Program | Purpose |
|---------|---------|
| **`Lucy-Setup.exe`** | Install, update, repair, pick version, developer mode |
| **`Lucy.exe`** | Launch the workspace (Pixi → Control Center) |

`windows/Lucy.py` is the PyInstaller source for `Lucy.exe`. It launches the workspace directly — there is no install menu. Use **`Lucy-Setup.exe`** for all install lifecycle tasks.

## Prerequisites

Install the following before running the project. After each installation, close and reopen any terminal so the updated `PATH` is picked up.

1. **Pixi** — [pixi.prefix.dev/latest/installation](https://pixi.prefix.dev/latest/installation/) (≥ 0.78 recommended).
2. **Git for Windows** — [git-scm.com/install/windows](https://git-scm.com/install/windows).
   - Required for `bash launch_lucy.sh` (default launch path).
   - Without Git, the installer downloads sub-repositories as ZIP archives.
3. **Python 3** (manual dev workflow only) — [python.org/downloads](https://www.python.org/downloads/).

GUI apps (RViz, Gazebo, rqt) run **natively** on Windows via RoboStack when OpenGL/display support is available. The control panel web viewer does not require a separate X server.

### CPU architecture (x64 / ARM64)

Pixi resolves **`win-64`** from `pixi.lock` on Intel/AMD and Windows-on-ARM hosts. Colcon uses `--merge-install` on Windows per RoboStack guidance.

## Installation (end users)

Download **`Lucy-Setup.exe`** from the [GitHub Releases](https://github.com/Sentience-Robotics/lucy_ws/releases) page (built automatically on version tags).

The installer:

- Installs Lucy to `%LOCALAPPDATA%\Programs\Lucy` (no admin required)
- Creates a **Start Menu** shortcut to `Lucy.exe`
- Lets you choose **Fresh install**, **Update**, or **Repair**
- Lets you pick a **lucy_ws version** (latest `master` or a release tag)
- Runs install/update after setup (clones sub-repos, `pixi install`, colcon build)
- Offers **Developer install** (off by default): requires Git, uses SSH clones and `DEV=true`

After setup, open **Lucy** from the Start Menu — it runs `bash launch_lucy.sh` and opens the Control Center.

To **update** or **repair**, run **`Lucy-Setup.exe`** again and pick the matching install mode.

### Control Panel

In the **Lucy Control Center**, enable **Core + Control Panel**. The panel is at [http://localhost:4004](http://localhost:4004). The launcher prints the exact URL when the panel is running.

## Manual install (developers)

Clone the repo, then install via CLI (same logic as the installer):

```powershell
cd C:\Users\<you>\lucy_ws
python windows\Lucy.py --cli install --repos-branch master
```

Or use Pixi directly from Git Bash / WSL:

```bash
python3 install.py
pixi run build
pixi run panel-install
```

Launch:

```powershell
python windows\Lucy.py
```

Or from Git Bash: `./launch_lucy.sh` or `python3 Lucy.py` (full TUI — see the main [README](../README.md)).

### Advanced CLI (installer internals)

`Lucy.exe --cli` is used by `Lucy-Setup.exe` and available for scripting:

```powershell
Lucy.exe --cli check-prereqs
Lucy.exe --cli install --repos-branch master
Lucy.exe --cli update
Lucy.exe --cli repair
Lucy.exe --cli install --developer --refresh-workspace --lucy-ws-ref v1.0.0 --lucy-ws-ref-type tag
```

### Building the installer locally

Requires [NSIS](https://nsis.sourceforge.io/Download) and PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File windows/build_installer.ps1
```

Outputs `dist\Lucy.exe` and `dist\Lucy-Setup-<version>.exe`.

### Application icon

The icon is [`windows/assets/lucy-icon.ico`](assets/lucy-icon.ico). To regenerate from a square logo JPG:

```powershell
pip install pillow
python -c "from PIL import Image; Image.open('path\to\lucy-logo.jpg').save('windows/assets/lucy-icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
```

## Terminal choice

- **Native Windows:** `Lucy.exe` (installed) or `python windows/Lucy.py` (from a clone) — uses Git Bash for launch.
- **Git Bash / WSL:** root `Lucy.py`, `install.py`, and `launch_lucy.sh` (recommended for developers).
