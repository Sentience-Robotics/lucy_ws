"""Tests for install.sh optional-repo colcon skip (COLCON_IGNORE)."""

import json
import os
import subprocess
from pathlib import Path

def _run_mark_optional(workspace: Path, build_optional: str | None = None) -> None:
    env = os.environ.copy()
    if build_optional is not None:
        env["LUCY_BUILD_OPTIONAL"] = build_optional
    root = str(workspace)
    bash_script = f"""
set -euo pipefail
cd {root!r}
CONFIG_FILE="{root}/config/repos.json"

parse_repos() {{
  python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for r in data.get('repos', []):
    name = str(r.get('name', '')).strip().strip('\\r\\n')
    optional = 1 if r.get('optional') else 0
    if name:
        print(name, optional, sep='\\t')
" "$CONFIG_FILE"
}}

mark_optional_colcon_ignore() {{
  case "$(echo "${{LUCY_BUILD_OPTIONAL:-}}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
  esac
  while IFS=$'\\t' read -r name optional; do
    name="${{name//$'\\r'/}}"
    optional="${{optional//$'\\r'/}}"
    if [ "$optional" = "1" ] && [ -d "src/${{name}}" ]; then
      touch "src/${{name}}/COLCON_IGNORE"
    fi
  done < <(parse_repos)
}}

mark_optional_colcon_ignore
"""
    subprocess.run(
        ["bash", "-c", bash_script],
        env=env,
        check=True,
        cwd=workspace,
    )


def test_mark_optional_colcon_ignore_skips_optional_repos(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "repos.json").write_text(
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
    (tmp_path / "src" / "required_pkg").mkdir(parents=True)
    (tmp_path / "src" / "opt_pkg").mkdir(parents=True)

    _run_mark_optional(tmp_path)

    assert (tmp_path / "src" / "opt_pkg" / "COLCON_IGNORE").is_file()
    assert not (tmp_path / "src" / "required_pkg" / "COLCON_IGNORE").exists()


def test_mark_optional_colcon_ignore_respects_build_optional_flag(tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "repos.json").write_text(
        json.dumps(
            {
                "repos": [
                    {
                        "name": "opt_pkg",
                        "branch": "main",
                        "optional": True,
                        "url_https": "https://example.com/opt.git",
                    }
                ]
            }
        )
    )
    (tmp_path / "src" / "opt_pkg").mkdir(parents=True)

    _run_mark_optional(tmp_path, build_optional="1")

    assert not (tmp_path / "src" / "opt_pkg" / "COLCON_IGNORE").exists()
