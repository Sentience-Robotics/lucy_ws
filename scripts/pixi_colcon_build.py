#!/usr/bin/env python3
"""
Windows-native colcon build wrapper.

Removes build/camera_ros before building, then runs colcon build with
the Windows workspace configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CAMERA_BUILD_DIR = ROOT / "build" / "camera_ros"


def main() -> int:
    if CAMERA_BUILD_DIR.exists():
        print(f"Removing {CAMERA_BUILD_DIR}")
        shutil.rmtree(CAMERA_BUILD_DIR)

    command = [
        "colcon",
        "build",
        "--merge-install",
        "--cmake-args",
        "-GNinja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-Wno-dev",
        *sys.argv[1:],
    ]

    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
