"""Platform-specific process introspection (Linux, macOS, Windows)."""

import os
import subprocess
import sys

from .constants import (
    LUCY_WS_MARKER,
    PIXI_ENV_MARKER,
    WORKSPACE_ROOT,
    _norm_path,
)


def path_in_text(text: str) -> bool:
    if not text:
        return False
    return _norm_path(LUCY_WS_MARKER) in _norm_path(text)


def _path_in_text(text: str) -> bool:
    return path_in_text(text)


def read_proc_cwd(pid: int) -> str:
    if sys.platform == "win32":
        return ""
    if sys.platform == "darwin":
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            if " cwd " in line:
                parts = line.split()
                if parts:
                    return parts[-1]
        return ""
    try:
        return os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return ""


def _read_proc_cwd(pid: int) -> str:
    return read_proc_cwd(pid)


def read_proc_environ_darwin(pid: int) -> dict[str, str]:
    """Parse env vars from ps eww by searching for KEY=… substrings (handles spaces in values)."""
    result = subprocess.run(
        ["ps", "eww", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    blob = result.stdout
    if not blob.strip():
        return {}
    keys = (
        "PIXI_PROJECT_MANIFEST",
        "CONDA_PREFIX",
        "GZ_SIM_RESOURCE_PATH",
        "GZ_SIM_SYSTEM_PLUGIN_PATH",
        "PWD",
        "PIXI_PROJECT_NAME",
    )
    env = {}
    for key in keys:
        marker = f"{key}="
        start = blob.find(marker)
        if start == -1:
            continue
        val_start = start + len(marker)
        end = len(blob)
        for other in keys:
            if other == key:
                continue
            pos = blob.find(f" {other}=", val_start)
            if pos != -1:
                end = min(end, pos)
        env[key] = blob[val_start:end].strip()
    return env


def _read_proc_environ_darwin(pid: int) -> dict[str, str]:
    return read_proc_environ_darwin(pid)


def read_proc_environ(pid: int) -> dict[str, str]:
    if sys.platform == "win32":
        return {}
    if sys.platform == "darwin":
        return read_proc_environ_darwin(pid)
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    env = {}
    for entry in raw.split(b"\0"):
        if b"=" not in entry:
            continue
        key, _, val = entry.partition(b"=")
        try:
            env[key.decode()] = val.decode(errors="replace")
        except UnicodeDecodeError:
            continue
    return env


def _read_proc_environ(pid: int) -> dict[str, str]:
    return read_proc_environ(pid)


def read_proc_exe(pid: int) -> str:
    if sys.platform == "win32":
        return ""
    if sys.platform == "darwin":
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def _read_proc_exe(pid: int) -> str:
    return read_proc_exe(pid)


def process_workspace_markers(pid: int) -> bool:
    """True when cwd, env, or binary ties a short-cmdline process to this workspace."""
    import launcher

    if pid <= 0:
        return False
    if sys.platform == "win32":
        ws = LUCY_WS_MARKER.replace("'", "''")
        script = (
            f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\"; "
            "if (-not $p) { exit 1 }; "
            f"if ($p.ExecutablePath -like '*{ws}*') {{ exit 0 }}; "
            f"if ($p.CommandLine -like '*{ws}*') {{ exit 0 }}; "
            "exit 1"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    if path_in_text(launcher._read_proc_cwd(pid)):
        return True
    exe = launcher._read_proc_exe(pid)
    if path_in_text(exe) or PIXI_ENV_MARKER in _norm_path(exe):
        return True
    env = launcher._read_proc_environ(pid)
    for key in (
        "PIXI_PROJECT_MANIFEST",
        "CONDA_PREFIX",
        "GZ_SIM_RESOURCE_PATH",
        "GZ_SIM_SYSTEM_PLUGIN_PATH",
        "PWD",
    ):
        if path_in_text(env.get(key, "")):
            return True
    if env.get("PIXI_PROJECT_NAME") == WORKSPACE_ROOT.name:
        return True
    return False


def _process_workspace_markers(pid: int) -> bool:
    return process_workspace_markers(pid)
