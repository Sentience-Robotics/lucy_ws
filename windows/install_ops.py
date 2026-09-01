"""
Windows-specific install glue for Lucy.

Used by windows/Lucy.py (launcher + CLI) and the NSIS installer via install_runner.py.

The actual install logic (repo fetching, Pixi bootstrap, colcon build) lives in the
cross-platform install.py at the repo root; this module adds only what is specific
to the packaged Windows flows: the install profile, host platform detection, and
refreshing the lucy_ws files themselves. Re-exports below keep the historical
install_ops.* API working for callers and the frozen Lucy.exe.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
import json
from datetime import datetime, timezone
from typing import Callable, Optional

_WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_WINDOWS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import install as _install  # noqa: E402

# --- re-exported cross-platform API (implemented in install.py) --------------
PrerequisiteError = _install.PrerequisiteError
REQUIREMENT_DOCS = _install.REQUIREMENT_DOCS
MIN_PIXI_VERSION = _install.MIN_PIXI_VERSION
DEFAULT_REPOS_BRANCH = _install.DEFAULT_REPOS_BRANCH
InstallMode = _install.InstallMode

git_available = _install.git_available
pixi_available = _install.pixi_available
python_available = _install.python_available
git_identity_warnings = _install.git_identity_warnings
check_prerequisites = _install.check_prerequisites
print_prerequisite_report = _install.print_prerequisite_report
require_prerequisites = _install.require_prerequisites
ensure_pixi = _install.ensure_pixi

parse_repos = _install.parse_repos
github_zip_url = _install.github_zip_url
fetch_repo = _install.fetch_repo
fetch_repo_git = _install.fetch_repo_git
fetch_repo_zip = _install.fetch_repo_zip
install_repos = _install.install_repos
mark_optional_colcon_ignore = _install.mark_optional_colcon_ignore
remove_workspace_src_repo = _install.remove_workspace_src_repo
remove_build_artifacts = _install.remove_build_artifacts
pixi_install = _install.pixi_install
build_workspace = _install.build_workspace

_safe_rmtree = _install.safe_rmtree

LUCY_WS_GITHUB = "Sentience-Robotics/lucy_ws"


# --- install profile ---------------------------------------------------------


def _repos_config_path(project_root: str) -> str:
    return str(_install.repos_config_path(project_root))


def install_profile_path(project_root: str) -> str:
    return os.path.join(project_root, "config", "install.profile.json")


def load_install_profile(project_root: str) -> dict:
    path = install_profile_path(project_root)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_install_profile(project_root: str, profile: dict) -> None:
    path = install_profile_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
        f.write("\n")


def default_profile(developer: bool = False, fetch_method: str = "git") -> dict:
    return {
        "lucy_ws_ref": "master",
        "lucy_ws_ref_type": "branch",
        "repos_branch": DEFAULT_REPOS_BRANCH,
        "fetch_method": fetch_method,
        "developer": developer,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def merge_profile(project_root: str, **overrides) -> dict:
    profile = default_profile()
    profile.update(load_install_profile(project_root))
    profile.update({k: v for k, v in overrides.items() if v is not None})
    return profile


# --- host platform -----------------------------------------------------------


def _native_machine() -> str:
    """Best-effort *native* CPU arch, seeing through Windows x64 emulation.

    A 64-bit x86 build of Lucy.exe runs emulated on Windows ARM, where
    platform.machine() reports AMD64. PROCESSOR_ARCHITEW6432 holds the true
    native arch in that WOW64/emulation case; fall back to the normal vars.
    """
    if sys.platform == "win32":
        for var in ("PROCESSOR_ARCHITEW6432", "PROCESSOR_ARCHITECTURE"):
            value = os.environ.get(var, "").strip().lower()
            if value:
                return value
    return platform.machine().lower()


def host_pixi_platform() -> str:
    """Map the native host to a Pixi platform id (pixi.toml / pixi.lock)."""
    machine = _native_machine()
    if sys.platform == "win32":
        return "win-64"
    if sys.platform == "darwin":
        if machine in ("aarch64", "arm64"):
            return "osx-arm64"
        return "osx-64"
    if machine in ("aarch64", "arm64"):
        return "linux-aarch64"
    return "linux-64"


def host_container_platform() -> str:
    """Legacy alias used by Windows CI — returns Pixi platform, not Docker."""
    return host_pixi_platform()


# --- dev mode ----------------------------------------------------------------


def set_dev_mode(project_root: str, enabled: bool) -> None:
    env_path = os.path.join(project_root, ".env")
    lines: list[str] = []
    dev_found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    with open(env_path, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip().startswith("DEV="):
                f.write(f"DEV={str(enabled).lower()}\n")
                dev_found = True
            else:
                f.write(line)
        if not dev_found:
            f.write(f"DEV={str(enabled).lower()}\n")


# --- flows -------------------------------------------------------------------


def run_install_flow(
    project_root: str,
    mode: InstallMode,
    *,
    developer: Optional[bool] = None,
    repos_branch: Optional[str] = None,
    fetch_method: Optional[str] = None,
    run_command: Callable,
    log: Callable[[str], None] = print,
) -> dict:
    """Full install/update/repair/build-only flow. Returns updated install profile."""
    profile = merge_profile(project_root)
    if developer is not None:
        profile["developer"] = developer
    if repos_branch is not None:
        profile["repos_branch"] = repos_branch
    if fetch_method is not None:
        profile["fetch_method"] = fetch_method

    dev = bool(profile.get("developer", False))
    # DEV lands in .env before the flow reads it, so SSH clones match the profile.
    set_dev_mode(project_root, dev)

    result = _install.run_flow(
        project_root,
        mode,
        developer=dev,
        repos_branch=profile.get("repos_branch", DEFAULT_REPOS_BRANCH),
        fetch_method=profile.get("fetch_method") or "auto",
        run_command=run_command,
        log=log,
    )

    profile["fetch_method"] = result["fetch_method"]
    profile["installed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_install_profile(project_root, profile)
    return profile


def fetch_lucy_ws_snapshot(
    project_root: str,
    ref: str,
    ref_type: str,
    *,
    fetch_method: str,
    run_command: Callable,
    log: Callable[[str], None] = print,
) -> None:
    """Refresh lucy_ws workspace files from GitHub at ref (branch or tag)."""
    use_git = fetch_method == "git" and git_available()

    if use_git and os.path.isdir(os.path.join(project_root, ".git")):
        log(f"Updating lucy_ws to {ref} ...")
        run_command(["git", "-C", project_root, "fetch", "origin"])
        run_command(["git", "-C", project_root, "checkout", ref])
        run_command(["git", "-C", project_root, "pull", "--ff-only", "origin", ref], check=False)
        return

    zip_url = (
        f"https://github.com/{LUCY_WS_GITHUB}/archive/refs/tags/{ref}.zip"
        if ref_type == "tag"
        else f"https://github.com/{LUCY_WS_GITHUB}/archive/refs/heads/{ref}.zip"
    )
    log(f"Downloading lucy_ws snapshot from {zip_url}")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "lucy_ws.zip")
        urllib.request.urlretrieve(zip_url, zip_path)
        extract_root = os.path.join(tmp, "extract")
        os.makedirs(extract_root, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            top_levels = {n.split("/")[0] for n in zf.namelist() if n.strip()}
            zf.extractall(extract_root)
        if len(top_levels) != 1:
            raise RuntimeError(f"Unexpected lucy_ws archive layout: {top_levels}")
        source = os.path.join(extract_root, next(iter(top_levels)))
        for name in os.listdir(source):
            if name in (".git", "src", "build", "install", "log"):
                continue
            src = os.path.join(source, name)
            dst = os.path.join(project_root, name)
            if os.path.isdir(dst):
                _safe_rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
