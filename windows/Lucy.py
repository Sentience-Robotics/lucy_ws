# Windows entry point for the Lucy workspace.
#
# Compiled to Lucy.exe via PyInstaller, and what the Start Menu / Desktop
# shortcuts run. With no arguments it installs the workspace when it is missing
# and otherwise names the pixi tasks. Lucy-Setup.exe drives install/update/
# repair through the hidden --cli mode (see windows/install_runner.py).
#
# PREREQUISITES:
# 1. Pixi — https://pixi.prefix.dev/latest/installation/
# 2. Workspace installed (run Lucy-Setup.exe first)

import os
import shutil
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

PIXI_TASKS = (
    ("pixi run core", "robot stack + rosbridge on 9090"),
    ("pixi run control-panel", "web UI on http://localhost:4004"),
    ("pixi run rviz", "optional viewer"),
)


def _workspace_built():
    install_dir = os.path.join(PROJECT_ROOT, "install")
    return (
        os.path.isfile(os.path.join(install_dir, "setup.bat"))
        or os.path.isfile(os.path.join(install_dir, "setup.bash"))
    )


def _is_cli_invocation():
    return len(sys.argv) > 1 and (sys.argv[1] == "--cli" or sys.argv[1] in _CLI_MODES)


def _run_cli(argv=None):
    """Install/update/repair — used by Lucy-Setup.exe, not exposed in the default UX."""
    from install_runner import main as install_main

    if argv is None:
        argv = [a for a in sys.argv[1:] if a != "--cli"]
    return install_main(argv)


def show_status():
    """Default action, i.e. what the Start Menu and Desktop shortcuts run.

    This used to hand off to launch_lucy.sh, which ends at the curses TUI that
    Windows has neither curses nor tmux for, so the shortcuts always failed.
    """
    if not _workspace_built():
        print("Lucy is not installed in this workspace.")
        return _run_cli(["install"])

    print(f"Lucy is installed in {PROJECT_ROOT}.")
    if shutil.which("pixi") is None:
        print(
            "Missing pixi. Install: https://pixi.prefix.dev/latest/installation/",
            file=sys.stderr,
        )
        return 1

    print("\nStart each component in its own terminal:")
    for command, purpose in PIXI_TASKS:
        print(f"  {command:<24} {purpose}")
    return 0


def _wait_before_closing():
    """A shortcut opens its own console, which would close before it is read."""
    if not getattr(sys, "frozen", False) or _is_cli_invocation():
        return
    try:
        input("\nPress Enter to close.")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    code = 0
    try:
        code = _run_cli() if _is_cli_invocation() else show_status()
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        code = 1
    _wait_before_closing()
    sys.exit(code)
