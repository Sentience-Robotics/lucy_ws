"""RP2040 serial access must be granted by a shipped udev rule, not group membership."""

import sys

import pytest

import install as installer


RULE = "99-lucy-rp2040.rules"


def test_rule_ships_in_the_repo():
    source = installer.udev_rule_source(installer.ROOT)
    assert source.is_file(), f"{RULE} must be committed for install.py to deploy it"
    text = source.read_text()
    # VID/PID the firmware declares and the host bridge scans for.
    assert 'ATTRS{idVendor}=="16c0"' in text
    assert 'ATTRS{idProduct}=="27dd"' in text
    assert 'SUBSYSTEM=="tty"' in text
    # 0666 rather than uaccess alone: uaccess grants nothing over SSH.
    assert 'MODE="0666"' in text


def test_is_current_detects_matching_and_diverged(tmp_path):
    rules_dir = tmp_path / "rules.d"
    rules_dir.mkdir()
    assert not installer.udev_rule_is_current(installer.ROOT, rules_dir)

    source = installer.udev_rule_source(installer.ROOT)
    (rules_dir / RULE).write_text(source.read_text())
    assert installer.udev_rule_is_current(installer.ROOT, rules_dir)

    (rules_dir / RULE).write_text("stale rule\n")
    assert not installer.udev_rule_is_current(installer.ROOT, rules_dir)


def test_already_current_runs_no_commands(tmp_path):
    rules_dir = tmp_path / "rules.d"
    rules_dir.mkdir()
    (rules_dir / RULE).write_text(installer.udev_rule_source(installer.ROOT).read_text())
    calls = []

    result = installer.ensure_rp2040_udev_rule(
        installer.ROOT,
        run_command=lambda cmd, **kw: calls.append(cmd),
        log=lambda _m: None,
        rules_dir=rules_dir,
    )
    if sys.platform.startswith("linux"):
        assert result is True
    assert calls == []


def test_skip_env_blocks_install(tmp_path, monkeypatch):
    monkeypatch.setenv("LUCY_SKIP_UDEV_RULE", "1")
    calls = []
    result = installer.ensure_rp2040_udev_rule(
        installer.ROOT,
        run_command=lambda cmd, **kw: calls.append(cmd),
        log=lambda _m: None,
        rules_dir=tmp_path,
    )
    assert result is False
    assert calls == []


def test_command_failure_is_not_fatal(tmp_path, monkeypatch):
    """A machine without sudo must still finish the install."""
    if not sys.platform.startswith("linux"):
        pytest.skip("udev rule only installs on Linux")
    monkeypatch.setenv("LUCY_UDEV_AUTO_INSTALL", "1")
    monkeypatch.delenv("LUCY_SKIP_UDEV_RULE", raising=False)
    monkeypatch.setattr(installer.shutil, "which", lambda _n: "/usr/bin/udevadm")

    def boom(cmd, **kw):
        raise OSError("no sudo here")

    messages = []
    result = installer.ensure_rp2040_udev_rule(
        installer.ROOT, run_command=boom, log=messages.append, rules_dir=tmp_path
    )
    assert result is False
    assert any("by hand" in m for m in messages)


def test_non_linux_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "darwin")
    calls = []
    result = installer.ensure_rp2040_udev_rule(
        installer.ROOT,
        run_command=lambda cmd, **kw: calls.append(cmd),
        log=lambda _m: None,
        rules_dir=tmp_path,
    )
    assert result is False
    assert calls == []
