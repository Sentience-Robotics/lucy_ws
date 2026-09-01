#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
JOINT_COMMAND_TOPIC = "/lucy/commanded_joint_states"


def configure_windows_dll_search_path() -> None:
    """Ensure ROS/Pixi native DLLs are available to the current process and child processes."""
    if os.name != "nt":
        return

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if not conda_prefix:
        return

    prefix = Path(conda_prefix)

    dll_directories = [
        prefix,
        prefix / "Library" / "bin",
        prefix / "Library" / "lib",
        prefix / "Scripts",
        prefix / "bin",
    ]
    dll_directories = [directory for directory in dll_directories if directory.is_dir()]

    # Older ROS/Conda installs on Windows can leave stale DLLs earlier on PATH and
    # cause import-time ABI mismatches when loading rclpy/_rclpy_pybind11.
    current_entries = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        lower = entry.lower()
        if "miniconda" in lower or "anaconda" in lower or "opt\\ros" in lower or "opt/ros" in lower:
            continue
        current_entries.append(entry)

    path_entries = [str(directory) for directory in dll_directories] + current_entries
    os.environ["PATH"] = os.pathsep.join(path_entries)

    handles = []
    for directory in dll_directories:
        try:
            handles.append(os.add_dll_directory(str(directory)))
        except (AttributeError, OSError):
            pass

    configure_windows_dll_search_path._handles = handles


def validate_windows_ros_runtime() -> None:
    """Fail early with a guided fix when the underlying ROS Python extension is broken."""
    if os.name != "nt":
        return

    try:
        import rclpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "ROS runtime is not healthy in this Pixi environment.\n"
            "This usually means a stale ROS/Conda install or missing Windows VC++ runtime is shadowing "
            "the RoboStack binaries.\n\n"
            "Fix:\n"
            "  1) Install Microsoft Visual C++ Redistributable 2015-2022 (x64)\n"
            "  2) Remove any old Anaconda/Miniconda/ROS installs from PATH\n"
            "  3) Recreate the environment: pixi install (or delete .pixi/envs/default and rerun pixi install)\n"
            "  4) Retry: pixi run core\n\n"
            f"Original import error: {exc}"
        ) from exc


def _joint_state_fallback_enabled() -> bool:
    """Whether to stand in for joint_state_broadcaster.

    controller_manager crashes on startup on win-64, so no controller spawns and
    nothing publishes /joint_states, leaving the control panel with no pose to
    draw. Set LUCY_JOINT_STATE_FALLBACK=0 once ros2_control works on Windows,
    otherwise this would publish alongside joint_state_broadcaster.
    """
    if os.name != "nt":
        return False
    value = os.environ.get("LUCY_JOINT_STATE_FALLBACK", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _start_joint_state_fallback():
    """Stand in for joint_state_broadcaster and joint_trajectory_controller.

    joint_command_echo turns the panel's trajectory commands into JointState, and
    joint_state_publisher merges that over the URDF's full joint list, so the
    model both renders and follows the controls.
    """
    commands = [
        [sys.executable, str(ROOT / "scripts" / "joint_command_echo.py")],
        [
            "ros2", "run", "joint_state_publisher", "joint_state_publisher",
            "--ros-args", "-p", f"source_list:=['{JOINT_COMMAND_TOPIC}']",
        ],
    ]
    started = []
    for command in commands:
        try:
            started.append(subprocess.Popen(command, cwd=ROOT))
        except OSError as exc:
            print(f"warning: could not start {command[0]}: {exc}", file=sys.stderr)
    return started


def _stop(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    configure_windows_dll_search_path()
    validate_windows_ros_runtime()

    robot = os.environ.get("LUCY_ROBOT_PACKAGE", "inmoov_urdf")

    command = [
        "ros2",
        "launch",
        "lucy_bringup",
        "lucy.launch.py",
        f"robot_package:={robot}",
        *sys.argv[1:],
    ]

    fallback = _start_joint_state_fallback() if _joint_state_fallback_enabled() else []
    try:
        return subprocess.call(command, cwd=ROOT)
    finally:
        for proc in fallback:
            _stop(proc)


if __name__ == "__main__":
    raise SystemExit(main())
