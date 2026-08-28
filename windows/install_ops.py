"""
Shared install logic for Lucy on Windows.

Used by windows/Lucy.py (launcher + CLI) and the NSIS installer via install_runner.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from typing import Callable, Optional

# Official install documentation (keep in sync with windows/README.md).
REQUIREMENT_DOCS = {
    "python": ("Python 3", "https://www.python.org/downloads/"),
    "git": ("Git for Windows", "https://git-scm.com/install/windows"),
    "docker": ("Docker Desktop", "https://docs.docker.com/desktop/setup/install/windows-install/"),
    "xserver": ("Windows X server (optional)", "https://github.com/marchaesen/vcxsrv/releases"),
}

LUCY_WS_GITHUB = "Sentience-Robotics/lucy_ws"
DEFAULT_REPOS_BRANCH = "master"
IMAGE_NAME = "lucy_ros2:jazzy"
WORKSPACE_CONTAINER = "/workspace"
DOCKER_PLATFORM_FILE = ".lucy-docker-platform"
DOCKER_IMAGE_LABEL = "lucy.dockerfile.sha256"

InstallMode = str  # "install" | "update" | "repair" | "build-only"


class PrerequisiteError(Exception):
    """Raised when required prerequisites are missing."""

    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__(self._format_issues(issues))

    @staticmethod
    def _format_issues(issues: list[dict]) -> str:
        lines = []
        for item in issues:
            if item.get("url"):
                lines.append(f"Missing {item['name']}. Install it: {item['url']}")
            else:
                lines.append(f"Missing {item['name']}: {item.get('detail', '')}")
        return "\n".join(lines)


def _repos_config_path(project_root: str) -> str:
    local_path = os.path.join(project_root, "config", "repos.json.local")
    default_path = os.path.join(project_root, "config", "repos.json")
    return local_path if os.path.exists(local_path) else default_path


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


def _run_quiet(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def git_available() -> bool:
    try:
        result = _run_quiet(["git", "--version"])
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def docker_available() -> bool:
    try:
        result = _run_quiet(["docker", "version"])
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def python_available() -> bool:
    try:
        result = _run_quiet([sys.executable, "--version"])
        return result.returncode == 0
    except OSError:
        return False


def git_identity_warnings() -> list[str]:
    warnings = []
    for key, label in (("user.name", "user.name"), ("user.email", "user.email")):
        result = _run_quiet(["git", "config", "--global", key])
        if result.returncode != 0 or not result.stdout.strip():
            warnings.append(f"Git {label} is not set (needed only if you commit changes).")
    return warnings


def check_prerequisites(
    developer: bool = False,
    require_python: bool = False,
) -> tuple[list[dict], list[str]]:
    """
    Return (blocking_issues, warnings).
    Each blocking issue: {id, name, url, detail}.
    """
    issues: list[dict] = []
    warnings: list[str] = []

    if require_python and not python_available():
        name, url = REQUIREMENT_DOCS["python"]
        issues.append({"id": "python", "name": name, "url": url, "detail": "python not found"})

    if not docker_available():
        name, url = REQUIREMENT_DOCS["docker"]
        issues.append({
            "id": "docker",
            "name": name,
            "url": url,
            "detail": "docker not found or Docker Desktop is not running",
        })

    if developer or not git_available():
        if not git_available():
            name, url = REQUIREMENT_DOCS["git"]
            entry = {"id": "git", "name": name, "url": url, "detail": "git not found in PATH"}
            if developer:
                issues.append(entry)
            else:
                warnings.append(
                    f"{name} not found; sub-repositories will be downloaded as ZIP archives. "
                    f"Install Git for full update support: {url}"
                )
        elif developer:
            warnings.extend(git_identity_warnings())

    return issues, warnings


def print_prerequisite_report(issues: list[dict], warnings: list[str]) -> None:
    for item in issues:
        print(f"ERROR: Missing {item['name']}. Install it: {item.get('url', '')}")
        if item.get("detail"):
            print(f"       {item['detail']}")
    for msg in warnings:
        print(f"WARNING: {msg}")


def require_prerequisites(developer: bool = False, require_python: bool = False) -> None:
    issues, warnings = check_prerequisites(developer=developer, require_python=require_python)
    print_prerequisite_report(issues, warnings)
    if issues:
        raise PrerequisiteError(issues)


def parse_repos(project_root: str, developer: bool, repos_branch: Optional[str] = None) -> list[dict]:
    config_path = _repos_config_path(project_root)
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    repos = []
    for repo in data.get("repos", []):
        name = repo.get("name", "").strip()
        if not name:
            continue
        branch = repos_branch or repo.get("branch", DEFAULT_REPOS_BRANCH)
        url_https = (repo.get("url_https") or repo.get("url") or "").strip()
        url_ssh = (repo.get("url_ssh") or "").strip()
        url = (url_ssh or url_https) if developer else (url_https or url_ssh)
        if url:
            repos.append({"name": name, "branch": branch, "url": url})
    return repos


def _github_slug_from_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    if "github.com/" in url:
        return url.split("github.com/", 1)[1]
    raise ValueError(f"Unsupported repository URL (expected GitHub HTTPS): {url}")


def github_zip_url(url: str, ref: str, ref_type: str = "branch") -> str:
    slug = _github_slug_from_url(url)
    if ref_type == "tag":
        return f"https://github.com/{slug}/archive/refs/tags/{ref}.zip"
    return f"https://github.com/{slug}/archive/refs/heads/{ref}.zip"


def _safe_rmtree(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def remove_workspace_src_repo(project_root: str, name: str, run_command: Callable) -> None:
    src_path = os.path.join(project_root, "src", name)
    _safe_rmtree(src_path)
    volume = format_volume_mapping(project_root, WORKSPACE_CONTAINER)
    run_command(
        [
            "docker", "run", "--rm",
            "-v", volume,
            IMAGE_NAME,
            "-c", f"rm -rf {WORKSPACE_CONTAINER}/src/{name}",
        ],
        check=False,
    )


def _extract_zip_to_dest(zip_path: str, dest: str, repo_name: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        top_levels = {name.split("/")[0] for name in zf.namelist() if name.strip()}
        zf.extractall(dest)
    if len(top_levels) != 1:
        raise RuntimeError(f"Unexpected archive layout for {repo_name}: {top_levels}")
    extracted = os.path.join(dest, next(iter(top_levels)))
    final = os.path.join(dest, repo_name)
    if os.path.exists(final):
        _safe_rmtree(final)
    os.rename(extracted, final)


def fetch_repo_zip(
    repo_name: str,
    url: str,
    branch: str,
    dest: str,
    log: Callable[[str], None],
) -> None:
    zip_url = github_zip_url(url, branch, ref_type="branch")
    log(f"Downloading {repo_name} from {zip_url}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, f"{repo_name}.zip")
        urllib.request.urlretrieve(zip_url, zip_path)
        parent = os.path.dirname(dest)
        _extract_zip_to_dest(zip_path, parent, repo_name)


def fetch_repo_git(
    repo_name: str,
    url: str,
    branch: str,
    dest: str,
    mode: str,
    run_command: Callable,
    log: Callable[[str], None],
) -> None:
    git_dir = os.path.join(dest, ".git")
    if mode == "repair" or not os.path.isdir(git_dir):
        if os.path.exists(dest):
            _safe_rmtree(dest)
        log(f"Cloning {repo_name} (branch {branch}) ...")
        run_command(["git", "clone", "-b", branch, url, dest])
        return

    log(f"Updating {repo_name} (branch {branch}) ...")
    run_command(["git", "-C", dest, "fetch", "origin"])
    checkout = run_command(["git", "-C", dest, "checkout", branch], check=False)
    if checkout != 0:
        run_command(["git", "-C", dest, "checkout", "-b", branch, f"origin/{branch}"])
    pull = run_command(["git", "-C", dest, "pull", "--ff-only", "origin", branch], check=False)
    if pull != 0:
        raise RuntimeError(
            f"Cannot fast-forward {repo_name} on {branch}. "
            "Merge/rebase locally or run Repair."
        )


def fetch_repo(
    repo_name: str,
    url: str,
    branch: str,
    dest: str,
    *,
    mode: str,
    fetch_method: str,
    developer: bool,
    run_command: Callable,
    log: Callable[[str], None],
) -> str:
    """Fetch a repo; returns effective fetch_method used ('git' or 'zip')."""
    use_git = fetch_method == "git" and git_available()
    if developer and not use_git:
        raise PrerequisiteError([{
            "id": "git",
            "name": REQUIREMENT_DOCS["git"][0],
            "url": REQUIREMENT_DOCS["git"][1],
            "detail": "Developer install requires Git",
        }])

    if use_git:
        fetch_repo_git(repo_name, url, branch, dest, mode, run_command, log)
        return "git"

    if mode != "repair" and os.path.isdir(os.path.join(dest, ".git")):
        log(f"Keeping existing git checkout for {repo_name} (git not available).")
        return "git"

    if os.path.exists(dest):
        _safe_rmtree(dest)
    fetch_repo_zip(repo_name, url, branch, dest, log)
    return "zip"


def install_repos(
    project_root: str,
    mode: InstallMode,
    *,
    developer: bool,
    repos_branch: Optional[str],
    fetch_method: str,
    run_command: Callable,
    log: Callable[[str], None] = print,
) -> str:
    """Install/update/repair sub-repositories. Returns effective fetch_method."""
    if mode == "build-only":
        return fetch_method

    repos = parse_repos(project_root, developer, repos_branch)
    if not repos:
        raise RuntimeError("No repositories defined in config/repos.json")

    src_dir = os.path.join(project_root, "src")
    os.makedirs(src_dir, exist_ok=True)

    effective_method = fetch_method
    for repo in repos:
        name = repo["name"]
        dest = os.path.join(src_dir, name)
        if mode == "repair":
            log(f"Repair: removing src/{name} ...")
            remove_workspace_src_repo(project_root, name, run_command)

        used = fetch_repo(
            name,
            repo["url"],
            repo["branch"],
            dest,
            mode=mode,
            fetch_method=effective_method,
            developer=developer,
            run_command=run_command,
            log=log,
        )
        if used == "zip":
            effective_method = "zip"

    if effective_method == "zip" and mode == "update":
        log("NOTE: ZIP-based install — local changes under src/ were replaced.")

    return effective_method


def format_volume_mapping(host_path: str, container_path: str) -> str:
    host_abs = os.path.abspath(host_path)
    return host_abs.replace("\\", "/") + ":" + container_path


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


def host_container_platform() -> str:
    """Map the host CPU to a Docker Linux platform (mirrors docker/ensure_image.sh)."""
    machine = _native_machine()
    if machine in ("x86_64", "amd64", "x86"):
        return "linux/amd64"
    if machine in ("aarch64", "arm64"):
        return "linux/arm64"
    return f"linux/{machine}"


def workspace_target_platform(project_root: str) -> str:
    """Target platform: LUCY_DOCKER_PLATFORM, then .lucy-docker-platform, then host arch."""
    override = os.environ.get("LUCY_DOCKER_PLATFORM", "").strip()
    if override:
        return override
    marker = os.path.join(project_root, DOCKER_PLATFORM_FILE)
    if os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8") as f:
                value = f.readline().strip()
            if value:
                return value
        except OSError:
            pass
    return host_container_platform()


def _platform_build_settings(target_platform: str) -> tuple[str, int]:
    """Return (base_image, install_vnc) for a target platform.

    The Jazzy image is built on ubuntu:24.04 (Noble); arm64 also enables the
    optional VNC desktop tooling in Dockerfile.jazzy.
    """
    base_image = "ubuntu:24.04"
    install_vnc = 1 if target_platform == "linux/arm64" else 0
    if os.environ.get("LUCY_FORCE_VNC", "").strip().lower() in ("1", "true", "yes"):
        install_vnc = 1
    return base_image, install_vnc


def _dockerfile_build_hash(dockerfile: str) -> str:
    """sha256 of the Dockerfile ignoring comments/blank lines (mirrors ensure_image.sh)."""
    kept = []
    with open(dockerfile, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            kept.append(line.rstrip())
    payload = ("\n".join(kept) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _current_image_label(image_name: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image_name,
             "--format", '{{index .Config.Labels "' + DOCKER_IMAGE_LABEL + '"}}'],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def docker_run_platform_args(project_root: str) -> list[str]:
    """`--platform <target>` so the daemon never guesses the run architecture."""
    return ["--platform", workspace_target_platform(project_root)]


def build_docker_image(
    project_root: str,
    run_command: Callable,
    log: Callable[[str], None] = print,
    force_rebuild: bool = False,
) -> None:
    dockerfile = os.path.join(project_root, "docker", "Dockerfile.jazzy")
    target_platform = workspace_target_platform(project_root)
    base_image, install_vnc = _platform_build_settings(target_platform)
    build_hash = _dockerfile_build_hash(dockerfile)
    want_label = f"{build_hash}|{target_platform}|vnc={install_vnc}"

    if not force_rebuild and _current_image_label(IMAGE_NAME) == want_label:
        log(f"Docker image {IMAGE_NAME} is up to date ({target_platform}); skipping build.")
        return

    log(f"Building Docker image for {target_platform} (base: {base_image})...")
    run_command([
        "docker", "build",
        "--platform", target_platform,
        "-f", dockerfile,
        "--build-arg", f"LUCY_FROM_PLATFORM={target_platform}",
        "--build-arg", f"LUCY_BASE_IMAGE={base_image}",
        "--build-arg", f"LUCY_INSTALL_VNC={install_vnc}",
        "--build-arg", f"DOCKERFILE_SHA256={build_hash}",
        "--build-arg", f"LUCY_DOCKER_BUILD_PLATFORM={target_platform}",
        "-t", IMAGE_NAME,
        project_root,
    ])


def build_workspace(project_root: str, run_command: Callable, log: Callable[[str], None] = print) -> None:
    log("Building workspace inside the container...")
    inner_cmd = (
        "source /opt/ros/jazzy/setup.bash && "
        "cd /workspace && "
        'rosdep install --from-paths src --ignore-src -r -y --skip-keys="audio_common thais_urdf" && '
        "rm -rf build/camera_ros install/camera_ros && "
        "colcon build --symlink-install && "
        'if [ -f src/lucy_control_panel/package.json ]; then '
        "(cd src/lucy_control_panel && yarn install); "
        "fi"
    )
    volume = format_volume_mapping(project_root, WORKSPACE_CONTAINER)
    run_command([
        "docker", "run", "--rm",
        *docker_run_platform_args(project_root),
        "-v", volume,
        IMAGE_NAME,
        "-c", inner_cmd,
    ])


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
    require_prerequisites(developer=dev)

    if mode != "build-only":
        effective = install_repos(
            project_root,
            mode,
            developer=dev,
            repos_branch=profile.get("repos_branch", DEFAULT_REPOS_BRANCH),
            fetch_method=profile.get("fetch_method", "git" if git_available() else "zip"),
            run_command=run_command,
            log=log,
        )
        profile["fetch_method"] = effective

    set_dev_mode(project_root, dev)
    build_docker_image(project_root, run_command, log, force_rebuild=(mode == "repair"))

    if mode in ("install", "update", "repair", "build-only"):
        build_workspace(project_root, run_command, log)

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
    url = f"https://github.com/{LUCY_WS_GITHUB}.git"
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
