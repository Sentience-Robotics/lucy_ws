"""Tests for launcher Pixi/tmux command wrapping (no tmux or ROS required)."""

import os

import launcher
from launcher import (
    STATE_FILE,
    WORKSPACE_ROOT,
    _gui_env_exports,
    _pixi_workspace_script,
    _tmux_new_pixi_window,
    load_workspace_env,
    needs_tmux_session,
)


def test_state_file_is_workspace_scoped():
    assert STATE_FILE == WORKSPACE_ROOT / ".lucy_launcher_modifiers.json"


def test_pixi_workspace_script_wraps_ros2():
    body = _pixi_workspace_script("ros2 doctor --report")
    assert f"cd {WORKSPACE_ROOT}" in body
    assert "pixi run -- ros2 doctor --report" in body


def test_pixi_workspace_script_preserves_pixi_command():
    body = _pixi_workspace_script("pixi run panel-dev")
    assert "pixi run panel-dev" in body
    assert "pixi run -- pixi" not in body


def test_pixi_workspace_script_complex_shell_uses_bash_lc():
    body = _pixi_workspace_script("echo hi && ros2 doctor")
    assert "pixi run -- bash -lc" in body


def test_gui_env_exports_forwards_display():
    os.environ["DISPLAY"] = ":1"
    exports = _gui_env_exports()
    assert "export DISPLAY=" in exports
    assert ":1" in exports
    del os.environ["DISPLAY"]


def test_tmux_new_pixi_window_wraps_in_bash_lc():
    cmd = _tmux_new_pixi_window("core", "ros2 launch pkg launch.py", remain_on_exit=True)
    assert "tmux new-window" in cmd
    assert "-n core" in cmd
    assert "bash -lc" in cmd
    assert "remain-on-exit on" in cmd


def test_load_workspace_env_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PORT_CONTROL_PANEL=5555\n")
    monkeypatch.setattr(launcher, "WORKSPACE_ROOT", tmp_path)
    os.environ.pop("PORT_CONTROL_PANEL", None)
    load_workspace_env()
    assert os.environ.get("PORT_CONTROL_PANEL") == "5555"


def test_needs_tmux_session_false_on_windows():
    if os.name == "nt":
        assert needs_tmux_session() is False
