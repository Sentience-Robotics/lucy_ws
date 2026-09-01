"""Launcher state, package status tracking, and UI helpers."""

import os
import time

from .constants import LOADING_TIMEOUT, STOPPING_TIMEOUT
from .config import get_dev_mode, load_state
from .package import Package, _pkg_visible


_pkg_start_times = {}  # pkg_id -> float, timestamp when start was issued
_intended_running = set()  # pkg_ids that should be running (for crash detection)
_pkg_stop_times = {}  # pkg_id -> float, timestamp when an async stop was issued


class LauncherState:
    def __init__(self, config_data):
        running_state = load_state()
        dev_mode = get_dev_mode()
        package_configs = [
            p for p in config_data["packages"] if _pkg_visible(p, dev_mode)
        ]
        self.packages = [Package(p, running_state["modifiers"]) for p in package_configs]
        self.package_map = {p.id: p for p in self.packages}

    def get_by_id(self, pkg_id):
        return self.package_map.get(pkg_id)

    def refresh_status(self):
        """Re-probe running/ready state for all packages without touching selected."""
        running_state = load_state()
        for pkg in self.packages:
            pkg.update_running_status(running_state["modifiers"])

    def _enable(self, pkg):
        """Tick a package, clearing anything it conflicts with first."""
        for conflict_id in pkg.conflicts:
            conflict_pkg = self.get_by_id(conflict_id)
            if conflict_pkg and conflict_pkg.selected:
                conflict_pkg.selected = False
        pkg.selected = True

    def _enable_with_deps(self, pkg):
        """Tick a package and any of its (transitive) dependencies that are off."""
        for dep_id in pkg.dependencies:
            dep = self.get_by_id(dep_id)
            if dep and not dep.selected:
                self._enable_with_deps(dep)
        self._enable(pkg)

    def _disable_with_dependents(self, pkg):
        """Untick a package and any (transitive) dependents."""
        for other_pkg in self.packages:
            if pkg.id in other_pkg.dependencies and other_pkg.selected:
                self._disable_with_dependents(other_pkg)
        pkg.selected = False

    def toggle(self, pkg_id):
        pkg = self.get_by_id(pkg_id)
        if not pkg:
            return None
        if pkg_id in _pkg_stop_times and not pkg.selected:
            return "Still stopping…"
        if not pkg.selected:
            self._enable_with_deps(pkg)
        else:
            self._disable_with_dependents(pkg)
        return None


def get_pkg_status(pkg):
    """Return one of: running, loading, crashed, stopped, stopping."""
    if pkg.id in _pkg_stop_times:
        if not pkg.is_running:
            _pkg_stop_times.pop(pkg.id, None)
            return "stopped"
        if time.time() - _pkg_stop_times[pkg.id] < STOPPING_TIMEOUT:
            return "stopping"
        _pkg_stop_times.pop(pkg.id, None)
    if pkg.pane_dead:
        _pkg_start_times.pop(pkg.id, None)
        if pkg.pane_exit_status == 0:
            _intended_running.discard(pkg.id)
            return "stopped"
        return "crashed"
    if pkg.ready:
        _pkg_start_times.pop(pkg.id, None)
        return "running"
    if pkg.id in _intended_running:
        timeout = getattr(pkg, "readiness_timeout", LOADING_TIMEOUT)
        started = _pkg_start_times.get(pkg.id)
        if started is None:
            if pkg.is_running:
                _pkg_start_times[pkg.id] = time.time()
                return "loading"
            return "crashed"
        if time.time() - started < timeout:
            return "loading"
        _pkg_start_times.pop(pkg.id, None)
        return "crashed"
    return "stopped"


def _has_unapplied_changes(state):
    for pkg in state.packages:
        if pkg.id in _pkg_start_times or pkg.id in _pkg_stop_times:
            continue
        if pkg.selected != pkg.is_running:
            return True
    return False


def _nav_hint(pkg):
    """Navigation hint for packages without a web URL (e.g. tmux terminal windows)."""
    if not pkg.nav_hint or not pkg.is_running:
        return ""
    return f"({pkg.nav_hint})"


def _status_url(pkg):
    """Expanded access URL for a package, or '' if unset env vars leave it unresolved."""
    if not pkg.url:
        return ""
    expanded = os.path.expandvars(pkg.url)
    if "${" in expanded or expanded.endswith(":"):
        return ""
    return expanded
