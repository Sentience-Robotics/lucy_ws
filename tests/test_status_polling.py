"""Tests for keeping slow status probes off the launcher's UI thread.

Readiness checks come from launcher_config.json as arbitrary shell, and core's
takes seconds (a `ros2 control list_controllers` behind a Pixi activation, and
longer still when controller_manager is down). Running them between getch()
calls freezes the TUI for the length of the slowest probe: a keypress lands only
once every probe has returned.
"""

import os
import subprocess
import threading
import time
from pathlib import Path

from launcher import StatusPoller

ROOT = Path(__file__).resolve().parents[1]


class FakeState:
    """Stands in for LauncherState with a probe of controllable duration."""

    def __init__(self, probe_seconds=0.0):
        self.probe_seconds = probe_seconds
        self.probes = 0
        self.probe_threads = []

    def probe_snapshot(self):
        self.probes += 1
        self.probe_threads.append(threading.current_thread())
        time.sleep(self.probe_seconds)
        return {"core": {"probes": self.probes}}


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_probes_run_off_the_calling_thread():
    state = FakeState(probe_seconds=0.2)
    poller = StatusPoller(state, interval=0.05)
    try:
        assert _wait_for(lambda: poller.take() is not None)
        assert all(t is not threading.current_thread() for t in state.probe_threads)
    finally:
        poller.stop()


def test_take_does_not_block_on_a_slow_probe():
    """The UI calls take() every frame; a probe in flight must not stall it."""
    state = FakeState(probe_seconds=30.0)
    poller = StatusPoller(state, interval=0.05)
    try:
        started = time.time()
        for _ in range(50):
            poller.take()
        assert time.time() - started < 1.0
    finally:
        poller.stop()


def test_snapshot_is_consumed_once():
    state = FakeState()
    poller = StatusPoller(state, interval=0.05)
    try:
        assert _wait_for(lambda: poller.take() is not None)
        assert poller.take() is None
    finally:
        poller.stop()


def test_request_refresh_discards_a_probe_started_before_it():
    """apply_changes() sets packages optimistically; a snapshot describing the
    world before that change would roll the display back to the old state."""
    state = FakeState(probe_seconds=0.3)
    poller = StatusPoller(state, interval=30.0)
    try:
        assert _wait_for(lambda: state.probes == 1)
        poller.request_refresh()
        time.sleep(0.5)
        stale, fresh = None, None
        for _ in range(200):
            got = poller.take()
            if got is not None:
                stale, fresh = fresh, got
            time.sleep(0.01)
        assert stale is None, "a snapshot from before request_refresh() was served"
        assert fresh is not None and fresh["core"]["probes"] > 1
    finally:
        poller.stop()


def test_idle_interval_stops_probing():
    state = FakeState()
    poller = StatusPoller(state, interval=0.05)
    try:
        assert _wait_for(lambda: state.probes >= 2)
        poller.set_interval(None)
        assert _wait_for(lambda: True)
        time.sleep(0.3)
        settled = state.probes
        time.sleep(0.5)
        assert state.probes == settled
        poller.request_refresh()
        assert _wait_for(lambda: state.probes > settled)
    finally:
        poller.stop()


def test_controllers_probe_caches_a_result_slower_than_its_ttl(tmp_path):
    """The cache is stamped when the probe finishes, not when it starts.

    `ros2 control list_controllers` routinely outruns the TTL — it waits on
    /controller_manager, up to LUCY_CONTROLLERS_TIMEOUT when the manager is
    down. Stamping at entry writes an entry that is already expired, so the
    expensive path, the only one worth caching, never produces a hit and every
    poll pays full price."""
    home = tmp_path / "home"
    (home / ".pixi" / "bin").mkdir(parents=True)
    fake_pixi = home / ".pixi" / "bin" / "pixi"
    fake_pixi.write_text("#!/usr/bin/env bash\nsleep 2\n")
    fake_pixi.chmod(0o755)

    env = {
        **os.environ,
        "HOME": str(home),
        "TMPDIR": str(tmp_path),
        "LUCY_CONTROLLERS_CACHE_TTL": "1",
        "LUCY_CONTROLLERS_TIMEOUT": "10",
    }
    script = str(ROOT / "scripts" / "controllers_active.sh")

    started = time.time()
    subprocess.run(["bash", script], cwd=ROOT, env=env, capture_output=True)
    cold = time.time() - started
    assert cold >= 2.0, "the probe was not actually exercised"

    started = time.time()
    subprocess.run(["bash", script], cwd=ROOT, env=env, capture_output=True)
    assert time.time() - started < 1.0, (
        "a probe slower than the TTL was not cached; every caller re-runs it"
    )


def test_timed_out_probe_leaves_no_orphaned_node(tmp_path):
    """`ros2 control` runs the rclpy node as a child of itself, so signalling
    only the handle the script holds leaves the node alive holding a DDS
    participant. The launcher polls core's readiness for as long as core is up,
    so one escapes per timed-out poll and they accumulate."""
    home = tmp_path / "home"
    (home / ".pixi" / "bin").mkdir(parents=True)
    child_pid_file = tmp_path / "child.pid"
    fake_pixi = home / ".pixi" / "bin" / "pixi"
    fake_pixi.write_text(
        "#!/usr/bin/env bash\n"
        "sleep 300 &\n"
        f"echo $! > {child_pid_file}\n"
        "sleep 300\n"
    )
    fake_pixi.chmod(0o755)

    subprocess.run(
        ["bash", str(ROOT / "scripts" / "controllers_active.sh")],
        cwd=ROOT,
        capture_output=True,
        env={
            **os.environ,
            "HOME": str(home),
            "TMPDIR": str(tmp_path),
            "LUCY_CONTROLLERS_TIMEOUT": "2",
        },
    )

    child_pid = int(child_pid_file.read_text().strip())
    assert _wait_for(lambda: not _alive(child_pid), timeout=5.0), (
        f"pid {child_pid} outlived the probe that spawned it"
    )


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_exit_prompt_survives_a_redraw_tick():
    """The prompt is loop state, not a blocking read.

    The loop repaints on a sub-second tick so live statuses stay current. A
    prompt that only existed between one getch() and the next was wiped by the
    following repaint, long before it could be read, let alone answered."""
    from launcher import confirm_exit_action

    assert confirm_exit_action(ord("y")) == "confirm"
    assert confirm_exit_action(ord("Y")) == "confirm"


def test_exit_prompt_stands_while_navigating():
    """Answering must stay possible after the selection moves under the prompt."""
    import curses

    from launcher import confirm_exit_action

    assert confirm_exit_action(curses.KEY_UP) == "keep"
    assert confirm_exit_action(curses.KEY_DOWN) == "keep"


def test_exit_prompt_is_dismissed_by_anything_else():
    """No stray keystroke may confirm a teardown of the running stack."""
    import curses

    from launcher import confirm_exit_action

    for key in (ord("n"), ord("N"), 27, ord(" "), ord("\n"), ord("q"), ord("x"), -1):
        assert confirm_exit_action(key) == "dismiss", f"key {key!r} did not dismiss"
