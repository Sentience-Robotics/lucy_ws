"""Entry point for `python -m launcher`."""

import os
import sys

try:
    import curses
except ImportError:
    curses = None

from .config import load_config, load_workspace_env
from .constants import STATE_FILE, TMUX_SESSION, WORKSPACE_ROOT
from .apply import stop_all_packages
from .shell import run_shell_command
from .state import LauncherState
from .tmux import is_in_tmux, needs_tmux_session
from .tui import main


def run():
    if curses is None:
        print(
            "Error: launcher TUI requires curses (not available on this platform).",
            file=sys.stderr,
        )
        sys.exit(1)
    load_workspace_env()
    if needs_tmux_session() and not is_in_tmux():
        print(
            f"Error: launcher must run inside the {TMUX_SESSION} tmux session (./launch_lucy.sh).",
            file=sys.stderr,
        )
        sys.exit(1)
    os.chdir(WORKSPACE_ROOT)

    status, state = None, None
    try:
        status, state = curses.wrapper(main)
    except KeyboardInterrupt:
        curses.endwin()
        print("\nStopping all processes and exiting workspace...")
        status = "ExitWorkspace"
        try:
            state = LauncherState(load_config())
        except Exception:
            state = None
    except Exception as e:
        curses.endwin()
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if status == "ExitWorkspace":
        print("\nStopping all processes and exiting workspace...")
        stop_all_packages(state)
        if STATE_FILE.is_file():
            STATE_FILE.unlink()
        if needs_tmux_session():
            print("Terminating tmux session...")
            run_shell_command(f"tmux kill-session -t {TMUX_SESSION} 2>/dev/null")


if __name__ == "__main__":
    run()
