# Windows Native TUI

This directory contains a Windows-native version of the main TUI (`Lucy.py`). It provides the same functionality as the Linux/macOS script but is designed to be run directly on Windows.

## How it Works

The script is a standalone Python application that calls `git.exe` and `docker.exe` directly. It does not have any external dependencies and can be run in a standard Windows Command Prompt or PowerShell.

It can also be compiled into a single `.exe` file using a tool like PyInstaller.

## Prerequisites

1.  **Python 3**: Must be installed and in your system's PATH.
2.  **Git for Windows**: Must be installed and in your system's PATH.
3.  **Docker Desktop**: Must be installed and running.

## Usage

From the project root, run the script using Python:

```bash
python windows/Lucy.py
```

You will be presented with a simple numbered menu to manage the workspace.
