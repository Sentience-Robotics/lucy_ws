"""Workspace-root unit tests (launcher helpers, install config)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SUPERVISOR_SRC = ROOT / "src" / "lucy_ros_packages" / "lucy_control_supervisor"
if SUPERVISOR_SRC.is_dir() and str(SUPERVISOR_SRC) not in sys.path:
    sys.path.insert(0, str(SUPERVISOR_SRC))
os.chdir(ROOT)
