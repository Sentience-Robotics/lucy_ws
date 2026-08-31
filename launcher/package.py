"""Package model and visibility helpers."""

import os

from .constants import LOADING_TIMEOUT, WORKSPACE_ROOT
from .config import save_state
from .shell import run_shell_command, _pane_exit_status


def _env_enabled(var_name):
    """True when a package has no env gate, or its `requires_env` var is truthy."""
    if not var_name:
        return True
    return os.environ.get(var_name, "").strip().lower() in ("1", "true", "yes")


def _ros_pkg_installed(pkg_name):
    """True when a ROS package is built in the workspace overlay (install/<pkg>)."""
    if not pkg_name:
        return True
    return (WORKSPACE_ROOT / "install" / pkg_name).is_dir()


def _pkg_visible(pkg_config, dev_mode):
    """Whether a package appears in the launcher."""
    if pkg_config.get("dev_only") and not dev_mode:
        return False
    if not _ros_pkg_installed(pkg_config.get("requires_pkg")):
        return False
    return _env_enabled(pkg_config.get("requires_env"))


class Package:
    def __init__(self, data, running_modifiers):
        self.id = data["id"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.type = data["type"]
        self.dependencies = data.get("dependencies", [])
        self.conflicts = data.get("conflicts", [])
        self.command = data.get("command", "")
        self.lifecycle_hooks = data.get("lifecycle_hooks", {})
        self.selected = data.get("default_on", False)
        self.requires_pkg = data.get("requires_pkg")
        self.subitem = data.get("subitem", False)
        self.readiness_check = data.get("readiness_check")
        self.readiness_timeout = data.get("readiness_timeout", LOADING_TIMEOUT)
        self.runs_on_vnc = data.get("runs_on_vnc", False)
        self.display_switch = data.get("display_switch", False)
        self.url = data.get("url")
        self.nav_hint = data.get("nav_hint", "")

        self.is_running = False
        self.ready = False
        self.pane_dead = False
        self.pane_exit_status = None
        self.update_running_status(running_modifiers)

        if self.type == "modifier" and self.requires_pkg:
            self.selected = self.is_running
        else:
            from .state import _pkg_stop_times

            if self.is_running and self.id not in _pkg_stop_times:
                self.selected = True

    def update_running_status(self, running_modifiers):
        if self.is_complex_command():
            self.is_running = run_shell_command(self.command["is_running"], capture_output=True)
        elif self.type == "modifier":
            self.is_running = self.id in running_modifiers
        elif self.type == "core":
            self.is_running = run_shell_command(
                f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'",
                capture_output=True,
            )
            if not self.is_running:
                save_state({"modifiers": []})
        elif self.type in ("tool", "interface"):
            self.is_running = run_shell_command(
                f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'",
                capture_output=True,
            )

        if not self.is_running:
            self.ready = False
        elif self.readiness_check:
            self.ready = run_shell_command(self.readiness_check, capture_output=True)
        else:
            self.ready = True

        self.pane_exit_status = _pane_exit_status(self.id) if self.is_running else None
        self.pane_dead = self.pane_exit_status is not None

    def is_complex_command(self):
        return isinstance(self.command, dict)
