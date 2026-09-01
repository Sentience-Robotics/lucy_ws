#!/usr/bin/env python3
"""CLI entry point for Lucy Windows install flows (used by Lucy.exe and the NSIS installer)."""

from __future__ import annotations

import argparse
import os
import sys

# Allow running as script from repo: python windows/install_runner.py
_WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import install_ops  # noqa: E402


def _project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(_WINDOWS_DIR)


def _make_run_command():
    def run_command(command, check=True, interactive=False):
        import subprocess
        print(f"--- Running: {' '.join(command)} ---")
        try:
            if interactive:
                return subprocess.run(command, check=check).returncode
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for line in iter(process.stdout.readline, ""):
                print(line.rstrip())
            process.wait()
            if check and process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command)
            return process.returncode
        except FileNotFoundError:
            print(f"Error: Command '{command[0]}' not found. Is it in your PATH?")
            if check:
                raise
            return -1
    return run_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lucy Windows install helper")
    parser.add_argument(
        "mode",
        choices=["install", "update", "repair", "build-only", "check-prereqs"],
        help="Install operation to run",
    )
    parser.add_argument("--developer", action="store_true", help="Developer install (requires git, SSH clones)")
    parser.add_argument("--repos-branch", default=None, help="Fallback branch for repos without one set")
    parser.add_argument("--lucy-ws-ref", default="master", help="lucy_ws git ref (branch or tag)")
    parser.add_argument(
        "--lucy-ws-ref-type",
        choices=["branch", "tag"],
        default="branch",
        help="Whether --lucy-ws-ref is a branch or tag",
    )
    parser.add_argument(
        "--fetch-method",
        choices=["git", "zip", "auto"],
        default="auto",
        help="How to fetch repositories",
    )
    parser.add_argument(
        "--refresh-workspace",
        action="store_true",
        help="Re-download lucy_ws files at --lucy-ws-ref before install",
    )
    parser.add_argument(
        "--launch-after",
        action="store_true",
        help="Launch the workspace after a successful install",
    )
    args = parser.parse_args(argv)

    root = _project_root()
    os.chdir(root)
    run_command = _make_run_command()

    if args.mode == "check-prereqs":
        issues, warnings = install_ops.check_prerequisites(developer=args.developer)
        install_ops.print_prerequisite_report(issues, warnings)
        return 1 if issues else 0

    fetch_method = args.fetch_method
    if fetch_method == "auto":
        fetch_method = "git" if install_ops.git_available() else "zip"

    profile = install_ops.merge_profile(
        root,
        lucy_ws_ref=args.lucy_ws_ref,
        lucy_ws_ref_type=args.lucy_ws_ref_type,
        repos_branch=args.repos_branch,
        fetch_method=fetch_method,
        developer=args.developer,
    )
    install_ops.save_install_profile(root, profile)

    if args.refresh_workspace:
        install_ops.fetch_lucy_ws_snapshot(
            root,
            args.lucy_ws_ref,
            args.lucy_ws_ref_type,
            fetch_method=fetch_method,
            run_command=run_command,
        )

    try:
        install_ops.run_install_flow(
            root,
            args.mode,
            developer=args.developer,
            repos_branch=args.repos_branch,
            fetch_method=fetch_method,
            run_command=run_command,
        )
    except install_ops.PrerequisiteError:
        return 1
    except Exception as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    print(f"--- Task '{args.mode}' finished successfully. ---")

    if args.launch_after and args.mode != "check-prereqs":
        print("\n--- Launching Lucy... ---")
        return _launch_workspace()

    return 0


def _launch_workspace() -> int:
    """Hand off to the workspace launcher in the current console window."""
    import Lucy  # noqa: WPS433  (Lucy.py exposes launch_workspace)
    Lucy.launch_workspace()
    return 0


if __name__ == "__main__":
    sys.exit(main())
