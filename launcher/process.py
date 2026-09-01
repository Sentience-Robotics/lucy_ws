"""Orphan process detection, iteration, and cleanup."""

import os
import signal
import subprocess
import sys
import threading
import time

from .constants import (
    CONTROL_PANEL_DIR,
    ORPHAN_CLEANUP_DEBOUNCE,
    _norm_path,
)
from .platform import (
    path_in_text,
    process_workspace_markers,
    read_proc_cwd,
)

_orphan_cleanup_timer = None
_orphan_cleanup_lock = threading.Lock()
_pending_preserve_windows: frozenset[str] = frozenset()
_pending_protect_vite: bool = False


def set_orphan_preserve_windows(package_window_ids, protect_vite=False):
    """Package tmux window ids to keep alive during the next orphan cleanup pass."""
    global _pending_preserve_windows, _pending_protect_vite
    if package_window_ids:
        _pending_preserve_windows = frozenset(package_window_ids)
    else:
        _pending_preserve_windows = frozenset()
    _pending_protect_vite = protect_vite


def _clear_orphan_preserve():
    global _pending_preserve_windows, _pending_protect_vite
    _pending_preserve_windows = frozenset()
    _pending_protect_vite = False


def _orphan_protected_by_preserve(
    cmdline: str,
    pid: int,
    preserve_package_windows: frozenset[str],
    protect_vite: bool,
) -> bool:
    """True when an orphan signature matches a package we are intentionally keeping."""
    if not preserve_package_windows and not protect_vite:
        return False
    if protect_vite and _is_vite_orphan(cmdline, pid):
        return True
    return False


def _is_gz_sim_cmdline(cmdline: str) -> bool:
    return "gz sim" in cmdline.lower()


def _matches_orphan_signature(cmdline: str) -> bool:
    """Cheap cmdline pre-filter — avoids /proc reads for unrelated processes."""
    if not cmdline:
        return False
    if (
        "launcher.py" in cmdline
        or "Lucy.py" in cmdline
        or "-m launcher" in cmdline
        or "launcher/__main__.py" in cmdline
        or "launcher/__main__" in cmdline
    ):
        return False
    cl = cmdline.lower()
    if _is_gz_sim_cmdline(cmdline):
        return True
    if "rosbridge_websocket" in cmdline:
        return True
    if "lucy.launch.py" in cmdline:
        return True
    if "rviz2" in cmdline:
        return True
    if "vite" in cl:
        return True
    return False


def _is_vite_orphan(cmdline: str, pid: int) -> bool:
    import launcher

    if "vite" not in cmdline.lower():
        return False
    if CONTROL_PANEL_DIR in _norm_path(cmdline):
        return True
    if pid > 0:
        cwd = launcher._read_proc_cwd(pid)
        if CONTROL_PANEL_DIR in _norm_path(cwd):
            return True
    return False


def _in_lucy_workspace(cmdline: str, pid: int) -> bool:
    import launcher

    if path_in_text(cmdline):
        return True
    if pid <= 0:
        return False
    return launcher._process_workspace_markers(pid)


def is_lucy_orphan(pid: int, cmdline: str) -> bool:
    """True when this process should be reaped during Lucy shutdown."""
    if not _matches_orphan_signature(cmdline):
        return False
    if not _in_lucy_workspace(cmdline, pid):
        return False
    if "vite" in cmdline.lower():
        return _is_vite_orphan(cmdline, pid)
    return True


def is_lucy_orphan_cmdline(cmdline: str) -> bool:
    """Cmdline-only check (when pid metadata is unavailable)."""
    return is_lucy_orphan(0, cmdline) and path_in_text(cmdline)


def _iter_processes():
    """Yield (pid, command_line) for all processes (Linux, macOS, Windows)."""
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process | "
            "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            pid_str, _, cmdline = line.partition("\t")
            try:
                yield int(pid_str.strip()), cmdline.strip()
            except ValueError:
                continue
        return
    result = subprocess.run(
        ["ps", "ax", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, cmdline = line.partition(" ")
        try:
            yield int(pid_str), cmdline.strip()
        except ValueError:
            continue


def _child_pids(pid: int) -> list[int]:
    if sys.platform == "win32":
        return []
    children = []
    if sys.platform == "darwin":
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,ppid="],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    cpid, ppid = int(parts[0]), int(parts[1])
                    if ppid == pid:
                        children.append(cpid)
                except ValueError:
                    continue
        return children
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        cpid = int(entry)
        try:
            with open(f"/proc/{cpid}/status") as f:
                for line in f:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        if ppid == pid:
                            children.append(cpid)
                        break
        except OSError:
            continue
    return children


def _kill_pid(pid: int):
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass


def _kill_process_tree(pid: int):
    for child in _child_pids(pid):
        _kill_process_tree(child)
    _kill_pid(pid)


def find_lucy_orphan_pids(
    *,
    exclude_pids=None,
    preserve_package_windows=None,
    protect_vite=False,
):
    """PIDs of workspace-scoped Lucy child processes (never the launcher itself)."""
    exclude = {os.getpid(), os.getppid()}
    if exclude_pids:
        exclude.update(exclude_pids)
    preserve = preserve_package_windows or frozenset()
    return [
        pid
        for pid, cmdline in _iter_processes()
        if pid not in exclude
        and not _orphan_protected_by_preserve(cmdline, pid, preserve, protect_vite)
        and is_lucy_orphan(pid, cmdline)
    ]


def cleanup_lucy_orphan_processes(
    preserve_package_windows=None,
    protect_vite=False,
):
    """Force-stop workspace-scoped orphan processes (cross-platform, scoped)."""
    preserve = preserve_package_windows or frozenset()
    for pid in find_lucy_orphan_pids(
        preserve_package_windows=preserve,
        protect_vite=protect_vite,
    ):
        _kill_process_tree(pid)


def wait_for_orphans_gone(
    timeout: float = 5.0,
    poll: float = 0.25,
    preserve_package_windows=None,
    protect_vite=False,
):
    """Block until find_lucy_orphan_pids() is empty or timeout elapses."""
    preserve = preserve_package_windows or frozenset()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not find_lucy_orphan_pids(
            preserve_package_windows=preserve,
            protect_vite=protect_vite,
        ):
            return
        time.sleep(poll)


def _finish_teardown(preserve_package_windows=None, protect_vite=None):
    explicit = preserve_package_windows is not None or protect_vite is not None
    if explicit:
        preserve = preserve_package_windows or frozenset()
        vite_protect = protect_vite if protect_vite is not None else False
    else:
        preserve = _pending_preserve_windows
        vite_protect = _pending_protect_vite
    cleanup_lucy_orphan_processes(
        preserve_package_windows=preserve,
        protect_vite=vite_protect,
    )
    wait_for_orphans_gone(
        timeout=10.0,
        preserve_package_windows=preserve,
        protect_vite=vite_protect,
    )
    cleanup_lucy_orphan_processes(
        preserve_package_windows=preserve,
        protect_vite=vite_protect,
    )
    if not explicit:
        _clear_orphan_preserve()


def _schedule_orphan_cleanup():
    """Debounced orphan cleanup — coalesces parallel async stops into one pass."""
    global _orphan_cleanup_timer

    def _fire():
        _finish_teardown()

    with _orphan_cleanup_lock:
        if _orphan_cleanup_timer is not None:
            _orphan_cleanup_timer.cancel()
        _orphan_cleanup_timer = threading.Timer(ORPHAN_CLEANUP_DEBOUNCE, _fire)
        _orphan_cleanup_timer.daemon = True
        _orphan_cleanup_timer.start()
