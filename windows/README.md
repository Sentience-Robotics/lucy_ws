# Windows Native TUI

This directory contains a Windows-native version of the main TUI (`Lucy.py`). It provides the same functionality as the Linux/macOS script but is designed to be run directly on Windows.

## How it Works

The script is a standalone Python application that calls `git.exe` and `docker.exe` directly. It does not have any external dependencies and can be run in a standard Windows Command Prompt or PowerShell.

It can also be compiled into a single `.exe` file using a tool like PyInstaller.

## Prerequisites

Install the following before running the project. After each installation, close and reopen any terminal so the updated `PATH` is picked up.

1.  **Python 3**: Download from [python.org/downloads](https://www.python.org/downloads/).
    - During setup, tick **"Add python.exe to PATH"** so `python` works from any terminal.
2.  **Git for Windows**: Download from [git-scm.com/install/windows](https://git-scm.com/install/windows).
    - The default options are fine; this also installs **Git Bash**.
3.  **Docker Desktop**: Download from [docs.docker.com/desktop/setup/install/windows-install](https://docs.docker.com/desktop/setup/install/windows-install/).
    - During installation, **uncheck "Use WSL 2 instead of Hyper-V"** unless you are an advanced/dev user who specifically needs the WSL 2 backend.
    - After install, **start Docker Desktop** and wait until it reports "running" before launching the project.
4.  **Windows X server** (optional): Required for GUI apps such as `rqt` inside the Docker container.
    - We recommend [VcXsrv](https://github.com/marchaesen/vcxsrv/releases).
    - Start VcXsrv on display `0`, allow TCP connections, and disable access control if needed.
    - Make sure Windows Firewall allows port `6000`.

> If you intend to solely use the control panel visualizer alongside command line tools, you can skip the installation of a third-party Windows X Server.

## Installation

### 1. Get the repository

You can either clone it with Git (recommended, makes updates easy) or download a ZIP.

**Option A — Clone with Git (recommended):**

```bash
git clone https://github.com/Sentience-Robotics/lucy_ws.git
```

**Option B — Download the ZIP:**

- Open the repository page on GitHub, click the green **Code** button, then **Download ZIP**.
- Extract the archive to a folder of your choice (for example `C:\Users\<you>\lucy_ws`).

### 2. Open a terminal and navigate to the project

1.  Open a terminal (see [Terminal choice](#terminal-choice) below). The quickest way: press **Win + R**, type `powershell`, and press Enter.
2.  Change into the folder where you cloned/extracted the repo using `cd`. For example:

```powershell
cd C:\Users\<you>\lucy_ws
```

> Tip: in File Explorer you can open the folder, then type `powershell` in the address bar and press Enter to open a terminal already pointing at that folder.

3.  Confirm you are in the right place — you should see `windows`, `config`, `Dockerfile.humble`, etc.:

```powershell
dir
```

### 3. Run the manager

From the project root, run the script using Python:

```bash
python windows/Lucy.py
```

**The first time, you must choose `Install / Update` in the menu** to clone the sub-repositories, build the Docker image, and build the workspace. This can take a while. Only after it completes should you use `Launch`.

### 4. Launch and open the Control Panel

Once the install has finished, run the manager again and choose **`Launch`**. In the **Lucy Control Center**, enable the **Control Panel** (and **Core**).

Once it is running, the **Lucy Control Panel is accessible in your browser at [http://localhost:5000](http://localhost:5000)** (or **http://localhost:5001** if port 5000 is already in use). The launcher also prints the exact URL next to the Control Panel entry once it is up.

## Usage

Running `python windows/Lucy.py` from the project root presents a simple numbered menu to manage the workspace (Launch, Install/Update, Rebuild, Developer Mode, Exit). Pressing Enter with no input defaults to **Launch**.

**On a fresh setup, always run `Install / Update` first**, then `Launch`.

## Terminal choice

To run the project, you will need to have access to a terminal, you have multiple choices:

- Default "command" application, will require `windows/Lucy.py`
- WSL, you will use the default `Lucy.py`. Be sure to enable WSL support in docker if you are using docker desktop
- Git bash, you will use the default `Lucy.py`.