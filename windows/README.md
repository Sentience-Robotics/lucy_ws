# Windows Native TUI

This directory contains a Windows-native version of the main TUI (`Lucy.py`). It provides the same functionality as the Linux/macOS script but is designed to be run directly on Windows.

## How it Works

The script is designed to be run from a **Git Bash** terminal. It executes the project's `.sh` scripts (`install.sh`, `launch_lucy.sh`) directly using the bash interpreter that comes with Git for Windows.

If the script is run outside of Git Bash, it will attempt to fall back to using **WSL (Windows Subsystem for Linux)**.

## Prerequisites

1.  **Git for Windows**: You must have Git for Windows installed, which includes Git Bash.
2.  **Docker Desktop**: Ensure Docker Desktop for Windows is installed and running.
3.  **Python 3**: Python must be installed on your Windows system.
4.  **questionary library**: This script depends on the `questionary` library to create the interactive command-line interface.

    Install it using pip:
    ```bash
    pip install questionary
    ```

## Usage

1.  **Open Git Bash**: Open a Git Bash terminal.
2.  **Navigate to the project root**: `cd /path/to/lucy_ws`
3.  **Run the script**:
    ```bash
    python windows/Lucy.py
    ```
