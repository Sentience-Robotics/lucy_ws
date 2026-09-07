#!/usr/bin/env python3

"""
Clean the colcon workspace.

Removes:
    build/
    install/
    log/

Works natively on Windows, Linux, and macOS.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from install import remove_build_artifacts  # noqa: E402


def main() -> None:
    remove_build_artifacts(ROOT)


if __name__ == "__main__":
    main()
