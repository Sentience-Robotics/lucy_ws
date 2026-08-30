"""Tests for install.sh repos.json parsing (HTTPS vs SSH, optional entries)."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PARSE_REPOS_SNIPPET = """
import json, os, sys

def clean(s):
    return str(s).strip().strip('\\r\\n')

use_ssh = os.environ.get('DEV', '').strip().lower() in ('1', 'true', 'yes')

with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = clean(r.get('name', ''))
    branch = clean(r.get('branch', 'main'))
    url_https = clean(r.get('url_https') or r.get('url') or '')
    url_ssh = clean(r.get('url_ssh') or '')
    url = (url_ssh or url_https) if use_ssh else (url_https or url_ssh)
    optional = 1 if r.get('optional') else 0
    if name and url:
        print(name, branch, url, optional, sep='\\t')
"""


def _parse_repos(config_path: Path, dev: bool = False) -> list[tuple[str, str, str, str]]:
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
        name, branch, url, optional = line.split("\t")
        rows.append((name, branch, url, optional))
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
    assert rows == [("foo_pkg", "main", "https://example.com/foo.git", "0")]


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
    assert rows == [("foo_pkg", "dev", "git@example.com:foo.git", "0")]


def test_parse_repos_marks_optional_repos(tmp_path):
    cfg = tmp_path / "repos.json"
    cfg.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "name": "required_pkg",
                        "branch": "main",
                        "url_https": "https://example.com/required.git",
                    },
                    {
                        "name": "opt_pkg",
                        "branch": "main",
                        "optional": True,
                        "url_https": "https://example.com/opt.git",
                    },
                ]
            }
        )
    )
    rows = _parse_repos(cfg)
    assert rows == [
        ("required_pkg", "main", "https://example.com/required.git", "0"),
        ("opt_pkg", "main", "https://example.com/opt.git", "1"),
    ]


def test_parse_repos_strips_carriage_returns(tmp_path):
    cfg = tmp_path / "repos.json"
    cfg.write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "name": "foo_pkg",
                        "branch": "main",
                        "url_https": "https://example.com/foo.git\r",
                    }
                ]
            }
        )
    )
    rows = _parse_repos(cfg)
    assert rows == [("foo_pkg", "main", "https://example.com/foo.git", "0")]


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
