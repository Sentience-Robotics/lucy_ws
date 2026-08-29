"""Tests for install.sh repos.json parsing (HTTPS vs SSH, optional entries)."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PARSE_REPOS_SNIPPET = """
import json, os, sys

use_ssh = os.environ.get('DEV', '').strip().lower() in ('1', 'true', 'yes')

with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = r.get('name', '').strip()
    branch = r.get('branch', 'main').strip()
    url_https = (r.get('url_https') or r.get('url') or '').strip()
    url_ssh = (r.get('url_ssh') or '').strip()
    url = (url_ssh or url_https) if use_ssh else (url_https or url_ssh)
    if name and url:
        print(name, branch, url, sep='\\t')
"""


def _parse_repos(config_path: Path, dev: bool = False) -> list[tuple[str, str, str]]:
    env = os.environ.copy()
    if dev:
        env["DEV"] = "true"
    else:
        env.pop("DEV", None)
    proc = subprocess.run(
        [sys.executable, "-c", PARSE_REPOS_SNIPPET, str(config_path)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    rows = []
    for line in proc.stdout.strip().splitlines():
        name, branch, url = line.split("\t")
        rows.append((name, branch, url))
    return rows


def test_parse_repos_https_default(tmp_path):
    cfg = tmp_path / "repos.json"
    cfg.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "name": "foo_pkg",
                        "branch": "main",
                        "url_https": "https://example.com/foo.git",
                        "url_ssh": "git@example.com:foo.git",
                    }
                ]
            }
        )
    )
    rows = _parse_repos(cfg)
    assert rows == [("foo_pkg", "main", "https://example.com/foo.git")]


def test_parse_repos_ssh_when_dev_true(tmp_path):
    cfg = tmp_path / "repos.json"
    cfg.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "name": "foo_pkg",
                        "branch": "dev",
                        "url_https": "https://example.com/foo.git",
                        "url_ssh": "git@example.com:foo.git",
                    }
                ]
            }
        )
    )
    rows = _parse_repos(cfg, dev=True)
    assert rows == [("foo_pkg", "dev", "git@example.com:foo.git")]


def test_tracked_repos_json_parses():
    cfg = ROOT / "config" / "repos.json"
    rows = _parse_repos(cfg)
    names = {r[0] for r in rows}
    assert "lucy_ros_packages" in names
    assert "micro_ros_agent" in names


def test_optional_flag_preserved_in_json():
    cfg = ROOT / "config" / "repos.json"
    data = json.loads(cfg.read_text())
    optional = [r["name"] for r in data["repos"] if r.get("optional")]
    assert "micro_ros_agent" in optional
    assert "audio_common" in optional
