# Windows Native TUI

This directory contains a Windows-native version of the main TUI (`Lucy.py`). It provides the same functionality as the Linux/macOS script but is designed to be run directly on Windows.

## How it Works

The script is a standalone Python application that calls `git.exe` and `docker.exe` directly. It does not have any external dependencies and can be run in a standard Windows Command Prompt or PowerShell.

It can also be compiled into a single `.exe` file using a tool like PyInstaller.

## Prerequisites

1.  **Python 3**: Must be installed and in your system's PATH.
2.  **Git for Windows**: Must be installed and in your system's PATH.
3.  **Docker Desktop**: Must be installed and running.
4.  **Windows X server**: Required for GUI apps such as `rqt` inside the Docker container.
    - We recommend [VcXsrv](https://github.com/marchaesen/vcxsrv/releases).
    - Start VcXsrv on display `0`, allow TCP connections, and disable access control if needed.
    - Make sure Windows Firewall allows port `6000`.

> If you intend to solely use the control panel visualizer alongside commande lines tools, you can skip the installation of a third-party Windows X Server.

## Usage

From the project root, run the script using Python:

```bash
python windows/Lucy.py
```

You will be presented with a simple numbered menu to manage the workspace.

## Terminal choice

To run the project, you will need to have access to a terminal, you have multiple choices:

- Default "command" application, will require `windows/Lucy.py`
- WSL, you will use the default `Lucy.py`. Be sure to enable WSL support in docker if you are using docker desktop
- Git bash, you will use the default `Lucy.py`.