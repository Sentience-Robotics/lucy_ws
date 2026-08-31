# Windows launcher for the Lucy workspace.
#
# Compiled to Lucy.exe via PyInstaller. Default behaviour: launch via Pixi
# (native RoboStack + Control Center launcher). Install/update/repair is handled
# by Lucy-Setup.exe via the hidden --cli mode (see windows/install_runner.py).
#
# PREREQUISITES:
# 1. Pixi — https://pixi.prefix.dev/latest/installation/
# 2. Git Bash (runs launch_lucy.sh) — https://git-scm.com/install/windows
# 3. Workspace installed (run Lucy-Setup.exe first)

import os
import shutil
import subprocess
import sys

if sys.platform != "win32":
    print("Error: This script is designed for Windows only.", file=sys.stderr)
    sys.exit(1)

_WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

if getattr(sys, "frozen", False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(_WINDOWS_DIR)

_CLI_MODES = frozenset(("install", "update", "repair", "build-only", "check-prereqs"))


def run_command(command, check=True, interactive=False):
    """Runs a command, streaming its output if not interactive."""
    print(f"--- Running: {' '.join(command)} ---")
    try:
        if interactive:
            return subprocess.run(command, check=check, cwd=PROJECT_ROOT).returncode
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=PROJECT_ROOT,
        )
        for line in iter(process.stdout.readline, ""):
            print(line.rstrip())
        process.wait()
        if check and process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        return process.returncode
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Is it in your PATH?")
        return -1
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        return e.returncode


def _workspace_built():
    install_dir = os.path.join(PROJECT_ROOT, "install")
    return (
        os.path.isfile(os.path.join(install_dir, "setup.bat"))
        or os.path.isfile(os.path.join(install_dir, "setup.bash"))
    )


def _find_git_bash():
    """Find Git for Windows bash.exe, never the WSL bash.exe."""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Git", "bin", "bash.exe"),
        os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"),
                     "Git", "bin", "bash.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     "Git", "bin", "bash.exe"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # Git Bash may also be discoverable through git.exe.
    git = shutil.which("git")
    if git:
        git_root = os.path.dirname(os.path.dirname(os.path.abspath(git)))
        candidate = os.path.join(git_root, "bin", "bash.exe")
        if os.path.isfile(candidate):
            return candidate

    return None


def launch_workspace():
    """Start Pixi and attach to the Lucy Control Center launcher."""
    if not _workspace_built():
        print(
            "Workspace not built. Run Lucy-Setup.exe to install or update first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if shutil.which("pixi") is None:
        print(
            "Missing pixi. Install: https://pixi.prefix.dev/latest/installation/",
            file=sys.stderr,
        )
        sys.exit(1)

    bash = _find_git_bash()
    launch_script = os.path.join(PROJECT_ROOT, "launch_lucy.sh")
    if not bash:
        print(
            "Git Bash (bash) is required to run launch_lucy.sh on Windows.",
            file=sys.stderr,
        )
        print("Install Git for Windows: https://git-scm.com/install/windows", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(launch_script):
        print(f"Missing launch script: {launch_script}", file=sys.stderr)
        sys.exit(1)

    print("Launching workspace...")
    run_command([bash, launch_script], interactive=True)


def _is_cli_invocation():
    return len(sys.argv) > 1 and (sys.argv[1] == "--cli" or sys.argv[1] in _CLI_MODES)


def _run_cli():
    """Install/update/repair — used by Lucy-Setup.exe, not exposed in the default UX."""
    from install_runner import main as install_main

    argv = [a for a in sys.argv[1:] if a != "--cli"]
    return install_main(argv)


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    try:
        if _is_cli_invocation():
            sys.exit(_run_cli())
        launch_workspace()
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
