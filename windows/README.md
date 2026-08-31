# Windows launcher and installer

On Windows, Lucy is split into two programs:

| Program | Purpose |
|---------|---------|
| **`Lucy-Setup.exe`** | Install, update, repair, pick version, developer mode |
| **`Lucy.exe`** | Launch the workspace (Docker → Lucy Control Center) |

`windows/Lucy.py` is the PyInstaller source for `Lucy.exe`. It launches the workspace directly — there is no install menu. Use **`Lucy-Setup.exe`** for all install lifecycle tasks.

## Prerequisites

Install the following before running the project. After each installation, close and reopen any terminal so the updated `PATH` is picked up.

1.  **Docker Desktop**: Download from [docs.docker.com/desktop/setup/install/windows-install](https://docs.docker.com/desktop/setup/install/windows-install/).
    - During installation, **uncheck "Use WSL 2 instead of Hyper-V"** unless you are an advanced/dev user who specifically needs the WSL 2 backend.
    - After install, **start Docker Desktop** and wait until it reports "running" before launching Lucy.
2.  **Git for Windows** (optional but recommended): Download from [git-scm.com/install/windows](https://git-scm.com/install/windows).
    - Without Git, the installer downloads sub-repositories as ZIP archives.
3.  **Python 3** (manual dev workflow only): Download from [python.org/downloads](https://www.python.org/downloads/).
4.  **Windows X server** (optional): Required for GUI apps such as `rqt` inside the Docker container.
    - We recommend [VcXsrv](https://github.com/marchaesen/vcxsrv/releases).
    - Start VcXsrv on display `0`, allow TCP connections, and disable access control if needed.
    - Make sure Windows Firewall allows port `6000`.

> If you intend to solely use the control panel visualizer alongside command line tools, you can skip the installation of a third-party Windows X Server.

### CPU architecture (x64 / ARM64)

The installer detects the host CPU automatically and builds the matching Docker image — `linux/amd64` on Intel/AMD PCs, `linux/arm64` on Windows-on-ARM devices. Native ARM detection works even though `Lucy.exe` itself is an x64 build running under emulation (it reads the true arch from `PROCESSOR_ARCHITEW6432`). To force a platform, set `LUCY_DOCKER_PLATFORM` (e.g. `linux/amd64`) before running, or drop a `.lucy-docker-platform` file in the install folder.

## Installation (end users)

Download **`Lucy-Setup.exe`** from the [GitHub Releases](https://github.com/Sentience-Robotics/lucy_ws/releases) page (built automatically on version tags).

The installer:

- Installs Lucy to `%LOCALAPPDATA%\Programs\Lucy` (no admin required)
- Creates a **Start Menu** shortcut to `Lucy.exe`
- Lets you choose **Fresh install**, **Update**, or **Repair**
- Lets you pick a **lucy_ws version** (latest `master` or a release tag)
- **Always runs Install/Update** after setup (opens a console — clones sub-repos on `master`, builds Docker image and workspace, then launches Lucy)
- Offers **Developer install** (off by default): requires Git, uses SSH clones and `DEV=true`

After setup, open **Lucy** from the Start Menu — it launches the workspace directly.

To **update** or **repair**, run **`Lucy-Setup.exe`** again and pick the matching install mode.

### Control Panel

In the **Lucy Control Center**, enable **Core + Control Panel**. Once it is running, the **Lucy Control Panel is accessible in your browser at [http://localhost:4004](http://localhost:4004)** (or the next free port if 4004 is already in use). The launcher also prints the exact URL next to the Control Panel entry once it is up.

## Manual install (developers)

Clone the repo, then run install via CLI (same logic as the installer):

```powershell
cd C:\Users\<you>\lucy_ws
python windows/Lucy.py --cli install --repos-branch master
```

Then launch:

```powershell
python windows/Lucy.py
```

Or use the root Linux manager if you prefer WSL/Git Bash: `python3 Lucy.py` (full menu — see the main [README](../README.md)).

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

- **Native Windows:** use `Lucy.exe` (installed) or `python windows/Lucy.py` (from a clone).
- **WSL / Git Bash:** use the root `Lucy.py` and `install.sh` / `launch_lucy.sh` instead.
