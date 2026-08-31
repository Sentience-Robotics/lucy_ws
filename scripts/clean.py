#!/usr/bin/env python3

"""
Clean the colcon workspace.

Removes:
    build/
    install/
    log/

Works natively on Windows, Linux, and macOS.
"""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent.parent


def remove(path: Path) -> None:
    if not path.exists():
        return

    if path.is_dir():
        print(f"Removing {path}")
        shutil.rmtree(path)
    else:
        print(f"Removing {path}")
        path.unlink()


def main() -> None:
    for name in ("build", "install", "log"):
        remove(ROOT / name)


if __name__ == "__main__":
    main()
