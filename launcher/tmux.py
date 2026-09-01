"""Tmux session and window management."""

import os
import sys

from .constants import TMUX_SESSION


def is_in_tmux():
    return "TMUX" in os.environ


def needs_tmux_session():
    """tmux launcher is used on Linux/macOS; Windows runs launcher directly."""
    return sys.platform not in ("win32", "cygwin", "msys") and os.name != "nt"


def _window_teardown_shell(window: str) -> str:
    """Gracefully stop a tmux window: SIGINT, brief poll wait, kill-window."""
    return (
        f"tmux send-keys -t {TMUX_SESSION}:{window} C-c 2>/dev/null; "
        "for _ in $(seq 1 8); do sleep 0.25; done; "
        f"tmux kill-window -t {TMUX_SESSION}:{window} 2>/dev/null"
    )


def _core_teardown_shell() -> str:
    return (
        f"tmux send-keys -t {TMUX_SESSION}:core C-c 2>/dev/null; "
        "for _ in $(seq 1 20); do "
        "pgrep -f '[g]z sim' >/dev/null 2>&1 || pgrep -x rviz2 >/dev/null 2>&1 || break; "
        "sleep 0.25; done; "
        f"tmux kill-window -t {TMUX_SESSION}:core 2>/dev/null"
    )


# Back-compat alias for tests / docs that referenced the shell snippet.
CORE_TEARDOWN = _core_teardown_shell()


def _stop_tmux_window(window: str):
    import launcher

    if launcher.needs_tmux_session():
        launcher.run_shell_command(launcher._window_teardown_shell(window))


def _stop_core_tmux():
    import launcher

    if launcher.needs_tmux_session():
        launcher.run_shell_command(launcher._core_teardown_shell())
