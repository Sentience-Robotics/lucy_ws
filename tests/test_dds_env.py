"""Tests for the DDS discovery scope exported before every ros2 call."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dds_env.sh"

PROBE = (
    "source scripts/dds_env.sh; "
    "echo \"range=${ROS_AUTOMATIC_DISCOVERY_RANGE-}\"; "
    "echo \"peers=${ROS_STATIC_PEERS-}\"; "
    "echo \"localhost_only=${ROS_LOCALHOST_ONLY-}\"; "
    "echo \"cyclone=${CYCLONEDDS_URI:+set}\""
)

CLEARED = ("CYCLONEDDS_URI", "LUCY_DDS_LOCALHOST", "LUCY_DDS_PEERS",
           "LUCY_DDS_RANGE", "LUCY_DDS_INTERFACE", "ROS_STATIC_PEERS",
           "ROS_AUTOMATIC_DISCOVERY_RANGE", "ROS_LOCALHOST_ONLY")


def _source(**overrides):
    """Source dds_env.sh with a clean slate plus overrides; return its exports."""
    cmd = ["env"] + [f"-u{name}" for name in CLEARED]
    cmd += [f"{k}={v}" for k, v in overrides.items()]
    cmd += ["bash", "-c", PROBE]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.strip().splitlines())


def test_discovery_is_scoped_to_localhost_by_default():
    assert _source()["range"] == "LOCALHOST"


def test_localhost_default_applies_on_every_platform():
    import platform

    assert _source()["range"] == "LOCALHOST", f"not applied on {platform.system()}"


def test_static_peers_are_additive_to_localhost():
    got = _source(LUCY_DDS_PEERS="hostA, hostB")
    assert got["peers"] == "hostA;hostB", "rcl splits ROS_STATIC_PEERS on ';'"
    assert got["range"] == "LOCALHOST"


def test_subnet_discovery_remains_available():
    assert _source(LUCY_DDS_LOCALHOST="0")["range"] == "SUBNET"


@pytest.mark.parametrize("value", ["OFF", "SUBNET", "SYSTEM_DEFAULT"])
def test_range_can_be_set_verbatim(value):
    assert _source(LUCY_DDS_RANGE=value)["range"] == value


def test_localhost_only_is_never_set():
    # Deprecated, and it takes precedence over the range set here.
    for overrides in ({}, {"LUCY_DDS_LOCALHOST": "0"}, {"LUCY_DDS_PEERS": "hostA"}):
        assert _source(**overrides)["localhost_only"] == ""


def test_explicit_cyclone_config_is_left_alone():
    cmd = ["env"] + [f"-u{n}" for n in CLEARED if n != "CYCLONEDDS_URI"]
    cmd += ["CYCLONEDDS_URI=<CycloneDDS/>", "bash", "-c",
            "source scripts/dds_env.sh; echo \"$CYCLONEDDS_URI\""]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert out.strip() == "<CycloneDDS/>"


def test_script_is_sourced_before_every_ros_command():
    shell = (ROOT / "launcher" / "shell.py").read_text()
    assert "_env_prelude" in shell and "_dds_source()" in shell
    assert "DDS_ENV_SCRIPT" in shell, "the prelude must source this script"
    assert "dds_env.sh" in (ROOT / "launcher" / "constants.py").read_text()
    assert "dds_env.sh" in (ROOT / "scripts" / "controllers_active.sh").read_text()
