"""Shell command execution, Pixi wrapping, and async runners."""

import os
import shlex
import subprocess
import threading

from .constants import (
    GUI_ENV_KEYS,
    NIX_GL_ENV_SCRIPT,
    TMUX_SESSION,
    WORKSPACE_ROOT,
)
from .process import _schedule_orphan_cleanup


def _gui_env_exports() -> str:
    parts = []
    for key in GUI_ENV_KEYS:
        val = os.environ.get(key)
        if val:
            parts.append(f"export {key}={shlex.quote(val)}")
    return "; ".join(parts)


def _nix_gl_source() -> str:
    """Source hook for NixOS: prepend host Mesa before Pixi conda GL (no-op elsewhere)."""
    if os.environ.get("LUCY_NIX_GL", "auto").lower() in ("0", "false", "no", "off"):
        return ""
    if not NIX_GL_ENV_SCRIPT.is_file():
        return ""
    return f"source {shlex.quote(str(NIX_GL_ENV_SCRIPT))}; "


def _pixi_workspace_script(user_cmd: str) -> str:
    """Shell script body: workspace root + Pixi env (RoboStack + colcon overlay)."""
    user_cmd = user_cmd.strip()
    nix_gl = _nix_gl_source()
    if user_cmd.startswith("pixi "):
        pixi_part = user_cmd
    elif nix_gl or any(op in user_cmd for op in (";", "&&", "||", "|", "&")):
        pixi_part = f"pixi run -- bash -lc {shlex.quote(nix_gl + user_cmd)}"
    elif user_cmd.startswith("ros2 "):
        pixi_part = f"pixi run -- bash -lc {shlex.quote(nix_gl + user_cmd)}"
    else:
        pixi_part = f"pixi run -- {user_cmd}"
    body = f"cd {WORKSPACE_ROOT} && {pixi_part}"
    exports = _gui_env_exports()
    if exports:
        body = f"{exports}; {body}"
    return body


def _tmux_new_pixi_window(window: str, user_cmd: str, remain_on_exit: bool = False) -> str:
    """Open a tmux window that runs user_cmd inside pixi run (tmux panes don't inherit pixi)."""
    inner = f"bash -lc {shlex.quote(_pixi_workspace_script(user_cmd))}"
    cmd = f"tmux new-window -d -t {TMUX_SESSION} -n {window} {inner}"
    if remain_on_exit:
        cmd += f"; tmux set-window-option -t {TMUX_SESSION}:{window} remain-on-exit on"
    return cmd


def _complex_package_start(pkg) -> str:
    """Legacy complex {start,stop,is_running} entries — route through Pixi when possible."""
    if pkg.id == "control_panel":
        return _tmux_new_pixi_window("control_panel", "pixi run panel-dev", remain_on_exit=True)
    return pkg.command["start"]


def run_shell_command(cmd, capture_output=False):
    if capture_output:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).returncode == 0
    subprocess.run(cmd, shell=True)


def run_shell_command_async(cmd, *, schedule_cleanup=False):
    """Fire a shell command without blocking the UI (daemon thread reaps the child).

    Used for stops so the TUI can show STOPPING while a slow shutdown runs.
    When schedule_cleanup is True, a debounced orphan cleanup runs afterward."""

    def _target():
        try:
            if cmd:
                subprocess.run(cmd, shell=True, check=False)
        except Exception:
            pass
        if schedule_cleanup:
            _schedule_orphan_cleanup()

    threading.Thread(target=_target, daemon=True).start()


def run_teardown_async(teardown_fn):
    """Run a tmux stop callable without blocking the UI; debounced orphan cleanup after."""

    def _target():
        try:
            teardown_fn()
        finally:
            _schedule_orphan_cleanup()

    threading.Thread(target=_target, daemon=True).start()


def _pane_exit_status(pkg_id):
    """Exit code of the package's dead tmux pane, or None if it isn't dead.
    remain-on-exit keeps the dead pane (and its output) so we can read the code:
    0 is a clean exit (STOPPED), anything else (incl. signal death) a crash (CRASHED)."""
    out = subprocess.run(
        f"tmux list-panes -t {TMUX_SESSION}:{pkg_id} -F '#{{pane_dead}}:#{{pane_dead_status}}' 2>/dev/null",
        shell=True,
        capture_output=True,
        text=True,
    ).stdout
    for line in out.splitlines():
        dead, _, status = line.strip().partition(":")
        if dead == "1":
            try:
                return int(status)
            except ValueError:
                return -1  # signal death reports no status; treat as a crash
    return None
