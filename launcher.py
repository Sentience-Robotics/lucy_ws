#!/usr/bin/env python3

import curses
import os
import sys
import subprocess
import threading
import time
import json

CONFIG_FILE = "/workspace/config/launcher_config.json"
STATE_FILE = "/tmp/launcher_state.json"
# Persisted across container restarts (lives on the bind-mounted workspace, not
# /tmp): the set of packages the user last applied, so ticks are remembered.
SELECTION_FILE = "/workspace/.lucy_launcher_state.json"
MIN_TERM_HEIGHT = 22
MIN_TERM_WIDTH = 65

LOADING_TIMEOUT = 30  # seconds before LOADING transitions to CRASHED
STOPPING_TIMEOUT = 30  # seconds to show STOPPING before giving up

_pkg_start_times = {}   # pkg_id -> float, timestamp when start was issued
_intended_running = set()  # pkg_ids that should be running (for crash detection)
_pkg_stop_times = {}    # pkg_id -> float, timestamp when an async stop was issued

# Tearing down the core window with `tmux kill-window` alone orphans the GUI
# processes ros2 launch spawned (notably `gz sim`), so they keep showing on the
# VNC desktop. Send SIGINT first for a clean ros2 launch shutdown, wait for the
# sim/RViz to exit, force-kill any stragglers, then remove the window.
CORE_TEARDOWN = (
    "tmux send-keys -t lucy_ws:core C-c 2>/dev/null; "
    "for _ in $(seq 1 12); do "
    "pgrep -f '[g]z sim' >/dev/null 2>&1 || pgrep -x rviz2 >/dev/null 2>&1 || break; sleep 0.25; "
    "done; "
    "pkill -f '[g]z sim' 2>/dev/null; pkill -x rviz2 2>/dev/null; "
    "tmux kill-window -t lucy_ws:core 2>/dev/null"
)

def get_dev_mode():
    env_path = "/workspace/.env"
    if not os.path.exists(env_path):
        return False
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("DEV="):
                return line.strip().split("=")[1].lower() == "true"
    return False

def is_in_docker():
    return os.path.exists('/.dockerenv')

def is_in_tmux():
    return 'TMUX' in os.environ

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_FILE}")
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"modifiers": []}
    with open(STATE_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"modifiers": []}

def save_state(state_data):
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f)

def load_selection():
    """Set of package ids the user last applied, or None if never saved."""
    if not os.path.exists(SELECTION_FILE):
        return None
    try:
        with open(SELECTION_FILE) as f:
            return set(json.load(f).get("selected", []))
    except (json.JSONDecodeError, OSError):
        return None

def save_selection(selected_ids):
    """Persist the applied tick selection so it is restored on the next launch."""
    try:
        with open(SELECTION_FILE, 'w') as f:
            json.dump({"selected": sorted(selected_ids)}, f)
    except OSError:
        pass

def run_shell_command(cmd, capture_output=False):
    if capture_output:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True).returncode == 0
    else:
        subprocess.run(cmd, shell=True)

def run_shell_command_async(cmd):
    """Fire a shell command without blocking the UI (daemon thread reaps the child).

    Used for stops so the TUI can show STOPPING while a slow shutdown runs."""
    def _target():
        try:
            subprocess.run(cmd, shell=True)
        except Exception:
            pass
    threading.Thread(target=_target, daemon=True).start()

def _pane_dead(pkg_id):
    """True if the package's tmux window exists but its process has exited.
    remain-on-exit keeps the dead pane (and its error output) for debugging."""
    return run_shell_command(
        f"tmux list-panes -t lucy_ws:{pkg_id} -F '#{{pane_dead}}' 2>/dev/null | grep -q '^1$'",
        capture_output=True,
    )

class Package:
    def __init__(self, data, running_modifiers):
        self.id = data['id']
        self.name = data['name']
        self.description = data.get('description', '')
        self.type = data['type']
        self.dependencies = data.get('dependencies', [])
        self.conflicts = data.get('conflicts', [])
        self.command = data.get('command', '')
        self.lifecycle_hooks = data.get('lifecycle_hooks', {})
        self.selected = data.get('default_on', False)
        # Robot-description package this entry selects (e.g. inmoov_urdf). When set,
        # the entry is hidden unless that package is built, so only installed robots
        # appear in the mutually-exclusive selector.
        self.requires_pkg = data.get('requires_pkg')
        # Render with a deeper indent so it reads as a sub-option of its dependency
        # (e.g. headless under "... with Simulator").
        self.subitem = data.get('subitem', False)
        # Optional shell probe that exits 0 only once the package is truly up.
        # Without it, a package is considered "ready" the instant its window exists.
        self.readiness_check = data.get('readiness_check')
        self.readiness_timeout = data.get('readiness_timeout', LOADING_TIMEOUT)
        # GUI app that renders to the in-container VNC desktop (Gazebo/RViz/rqt):
        # drives the "(VNC)" hint and skips the tmux auto-switch on launch.
        self.runs_on_vnc = data.get('runs_on_vnc', False)
        # Toggling this package switches the in-container virtual display on/off.
        self.display_switch = data.get('display_switch', False)
        # Access URL shown after [RUNNING] (control panel / VNC endpoints). May
        # reference env vars as ${VAR} — expanded at render time.
        self.url = data.get('url')

        # is_running = window/process exists; ready = readiness probe passed;
        # pane_dead = service window kept open after its process crashed.
        self.is_running = False
        self.ready = False
        self.pane_dead = False
        self.update_running_status(running_modifiers)

        # Robot-package radios are mutually exclusive
        if self.type == 'modifier' and self.requires_pkg:
            self.selected = self.is_running
        # Reflect running state as ticked — but not while it is being stopped, so an
        # in-progress shutdown doesn't re-check the box the user just unticked.
        elif self.is_running and self.id not in _pkg_stop_times:
            self.selected = True

    def update_running_status(self, running_modifiers):
        if self.is_complex_command():
            self.is_running = run_shell_command(self.command['is_running'], capture_output=True)
        elif self.type == 'modifier':
            self.is_running = self.id in running_modifiers
        elif self.type == 'core':
            self.is_running = run_shell_command(f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'", capture_output=True)
            if not self.is_running:
                save_state({"modifiers": []})
        elif self.type in ['tool', 'interface']:
             self.is_running = run_shell_command(f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'", capture_output=True)

        # Derive readiness: only meaningful while the window/process exists.
        if not self.is_running:
            self.ready = False
        elif self.readiness_check:
            self.ready = run_shell_command(self.readiness_check, capture_output=True)
        else:
            self.ready = True

        # A service whose window is still up (remain-on-exit) but whose process
        # has exited: reported as CRASHED while the error stays visible.
        self.pane_dead = (
            self.is_running and bool(self.readiness_check)
            and not self.ready and _pane_dead(self.id)
        )

    def is_complex_command(self):
        return isinstance(self.command, dict)

def _env_enabled(var_name):
    """True when a package has no env gate, or its `requires_env` var is truthy.

    Lets entries like the VNC/noVNC viewers appear only where they make sense
    (the in-container virtual desktop sets LUCY_GUI_VNC=1; a normal Linux host
    with native X11 leaves it unset, hiding them)."""
    if not var_name:
        return True
    return os.environ.get(var_name, "").strip().lower() in ("1", "true", "yes")

def _ros_pkg_installed(pkg_name):
    """True when a ROS package is built in the workspace overlay (install/<pkg>).

    Used to gate the robot-package selector entries so only robots that are
    actually built show up — mirrors lucy.launch.py's runtime discovery."""
    if not pkg_name:
        return True
    return os.path.isdir(os.path.join("/workspace", "install", pkg_name))

def _pkg_visible(pkg_config, dev_mode):
    """Whether a package appears in the launcher: hidden when it is `dev_only` and
    Developer Mode is off, when its `requires_env` gate isn't satisfied, or when a
    `requires_pkg` robot package isn't built."""
    if pkg_config.get('dev_only') and not dev_mode:
        return False
    if not _ros_pkg_installed(pkg_config.get('requires_pkg')):
        return False
    return _env_enabled(pkg_config.get('requires_env'))

class LauncherState:
    def __init__(self, config_data):
        running_state = load_state()
        # Hide gated packages before building them, so their readiness probes don't run and they don't render.
        dev_mode = get_dev_mode()
        package_configs = [
            p for p in config_data['packages'] if _pkg_visible(p, dev_mode)
        ]
        self.packages = [Package(p, running_state['modifiers']) for p in package_configs]
        self.package_map = {p.id: p for p in self.packages}

    def get_by_id(self, pkg_id):
        return self.package_map.get(pkg_id)

    def refresh_status(self):
        """Re-probe running/ready state for all packages without touching selected.

        Used by the poll timer so in-flight user tick changes aren't wiped out
        between keypresses (LauncherState.__init__ resets selected to default_on)."""
        running_state = load_state()
        for pkg in self.packages:
            pkg.update_running_status(running_state['modifiers'])

    def _enable(self, pkg):
        """Tick a package, clearing anything it conflicts with first."""
        for conflict_id in pkg.conflicts:
            conflict_pkg = self.get_by_id(conflict_id)
            if conflict_pkg and conflict_pkg.selected:
                conflict_pkg.selected = False
        pkg.selected = True

    def _enable_with_deps(self, pkg):
        """Tick a package and any of its (transitive) dependencies that are off, so a
        sub-option pulls in its parent (e.g. headless ticks the simulator)."""
        for dep_id in pkg.dependencies:
            dep = self.get_by_id(dep_id)
            if dep and not dep.selected:
                self._enable_with_deps(dep)
        self._enable(pkg)

    def _disable_with_dependents(self, pkg):
        """Untick a package and any (transitive) dependents, so turning off a parent
        also turns off its sub-options (e.g. unticking core drops the simulator and
        headless together rather than leaving them orphaned)."""
        for other_pkg in self.packages:
            if pkg.id in other_pkg.dependencies and other_pkg.selected:
                self._disable_with_dependents(other_pkg)
        pkg.selected = False

    def toggle(self, pkg_id):
        pkg = self.get_by_id(pkg_id)
        if not pkg: return None
        if pkg_id in _pkg_stop_times and not pkg.selected:
            return "Still stopping…"
        if not pkg.selected:
            # Ticking any option auto-enables its (transitive) dependencies instead
            # of being blocked — e.g. the simulator/RViz/a robot pulls in core, and
            # headless pulls in the simulator.
            self._enable_with_deps(pkg)
        else:
            self._disable_with_dependents(pkg)
        return None

def get_pkg_status(pkg):
    """Return one of: running, loading, crashed, stopped.

    ``pkg.is_running`` means the tmux window / process merely exists; ``pkg.ready``
    means its readiness probe passed (the stack is actually up). A package we
    started (in ``_intended_running``) that isn't ready yet shows LOADING until its
    timeout elapses, after which it is reported CRASHED. A package being shut down
    (in ``_pkg_stop_times``) shows STOPPING until its process is gone.
    """
    if pkg.id in _pkg_stop_times:
        if not pkg.is_running:
            _pkg_stop_times.pop(pkg.id, None)
            return "stopped"
        if time.time() - _pkg_stop_times[pkg.id] < STOPPING_TIMEOUT:
            return "stopping"
        _pkg_stop_times.pop(pkg.id, None)  # gave up; fall through to real state
    # Service window left open by a crash (remain-on-exit): CRASHED right away,
    # no waiting for the loading timeout, so the error can be read in tmux.
    if pkg.pane_dead:
        _pkg_start_times.pop(pkg.id, None)
        return "crashed"
    if pkg.ready:
        _pkg_start_times.pop(pkg.id, None)
        return "running"
    if pkg.id in _intended_running:
        timeout = getattr(pkg, "readiness_timeout", LOADING_TIMEOUT)
        started = _pkg_start_times.get(pkg.id)
        if started is None:
            if pkg.is_running:
                _pkg_start_times[pkg.id] = time.time()
                return "loading"
            return "crashed"
        if time.time() - started < timeout:
            return "loading"
        _pkg_start_times.pop(pkg.id, None)
        return "crashed"
    return "stopped"

def _has_unapplied_changes(state):
    for pkg in state.packages:
        if pkg.id in _pkg_start_times or pkg.id in _pkg_stop_times:
            continue
        if pkg.selected != pkg.is_running:
            return True
    return False

def _vnc_hint(pkg, state):
    """'(VNC)' for GUI packages when the virtual desktop is active (a display_switch
    package is running). Tells the user the window appears in the VNC viewer."""
    if not pkg.runs_on_vnc or not pkg.selected:
        return ""
    if any(p.display_switch and p.is_running for p in state.packages):
        return "(VNC)"
    return ""

def _status_url(pkg):
    """Expanded access URL for a package, or '' if it has none / an env var in it
    is unset (so we never show a half-resolved 'localhost:${...}')."""
    if not pkg.url:
        return ""
    expanded = os.path.expandvars(pkg.url)
    if "${" in expanded or expanded.endswith(":"):
        return ""
    return expanded

def _draw_pkg_row(stdscr, y, x, prefix, indent, checkbox, name, attr, status, hint="", url=""):
    base = f"{prefix}{indent}{checkbox} {name}"
    stdscr.addstr(y, x, base, attr)
    col = x + len(base)
    labels = {
        "running": (" [RUNNING]", curses.color_pair(4)),
        "loading": (" [LOADING]", curses.color_pair(1)),
        "stopping": (" [STOPPING]", curses.color_pair(1)),
        "crashed": (" [CRASHED]", curses.color_pair(2) | curses.A_BOLD),
        "stopped": (" [STOPPED]", curses.A_DIM),
    }
    status_str, status_attr = labels.get(status, (" [STOPPED]", curses.A_DIM))
    try:
        stdscr.addstr(y, col, status_str, status_attr)
        col += len(status_str)
    except curses.error:
        pass
    # Access URL after the status, shown only while actually running.
    if url and status == "running":
        text = f" ({url})"
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))  # cyan
            col += len(text)
        except curses.error:
            pass
    # '(VNC)' reminder after the status label.
    if hint:
        text = f" {hint}"
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))  # cyan
            col += len(text)
        except curses.error:
            pass

def draw_too_small_message(stdscr):
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    message = "Please increase terminal size"
    message2 = f"({MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} required)"
    stdscr.addstr(h // 2 - 1, max(0, (w - len(message)) // 2), message, curses.A_BOLD)
    stdscr.addstr(h // 2, max(0, (w - len(message2)) // 2), message2, curses.A_DIM)
    stdscr.refresh()

def draw_tui(stdscr, state, current_idx, error_msg, status_msg, unapplied=False):
    h, w = stdscr.getmaxyx()
    if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
        draw_too_small_message(stdscr)
        return None

    stdscr.clear()
    title = "Lucy Control Center"
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
    stdscr.addstr(h - 1, 2, "Enter: Apply | Space: Toggle | X: Stop All & Exit Docker", curses.A_BOLD)

    if status_msg:
        stdscr.addstr(h - 2, 2, status_msg, curses.A_BOLD)
    elif error_msg:
        stdscr.addstr(h - 2, 2, f"Warning: {error_msg}", curses.color_pair(2))
    elif unapplied:
        stdscr.addstr(h - 2, 2, "Unapplied changes — press Enter to apply", curses.color_pair(1))

    # Robot-package selectors are modifiers (their command is appended to the core
    # launch), but get their own section so the robot choice reads as a distinct
    # group rather than another core toggle.
    robots = [p for p in state.packages if p.type == 'modifier' and p.requires_pkg]
    cores_and_mods = [p for p in state.packages if p.type in ['core', 'modifier'] and not p.requires_pkg]
    interfaces = [p for p in state.packages if p.type == 'interface']
    tools = [p for p in state.packages if p.type == 'tool']
    display_list = cores_and_mods + robots + interfaces + tools

    def draw_section(title, color, items, offset, gap=1, indent_all=False):
        nonlocal row
        stdscr.addstr(row, 2, title, curses.A_BOLD | color)
        row += gap
        for i, p in enumerate(items):
            list_idx = offset + i
            prefix = "> " if current_idx == list_idx else "  "
            checkbox = "[x]" if p.selected else "[ ]"
            can_enable = all(state.get_by_id(dep).selected for dep in p.dependencies)
            attr = curses.A_NORMAL if can_enable else curses.A_DIM
            if p.type == 'core':
                attr |= curses.A_BOLD
            if p.subitem:
                indent = "        "
            elif indent_all or p.type == 'modifier':
                indent = "    "
            else:
                indent = ""
            status = get_pkg_status(p)
            _draw_pkg_row(stdscr, row + i, 4, prefix, indent, checkbox, p.name, attr,
                          status, _vnc_hint(p, state), _status_url(p))
        row += len(items) + 1

    row = 2
    draw_section("Primary Launch Targets", curses.color_pair(1), cores_and_mods, 0, gap=2)
    offset = len(cores_and_mods)
    if robots:
        draw_section("Robot", curses.color_pair(1), robots, offset, gap=1, indent_all=True)
        offset += len(robots)
    draw_section("Interfaces", curses.color_pair(3), interfaces, offset, gap=1)
    offset += len(interfaces)
    draw_section("Tools", curses.color_pair(3), tools, offset, gap=1)

    stdscr.refresh()
    return display_list

def apply_changes(state):
    last_launched_window = None
    core_pkg = state.get_by_id('core')
    
    # Check if core modifiers have changed
    modifiers_changed = False
    if core_pkg and core_pkg.selected:
        selected_modifier_ids = set(p.id for p in state.packages if p.type == 'modifier' and p.selected)
        running_modifier_ids = set(p.id for p in state.packages if p.type == 'modifier' and p.is_running)
        if selected_modifier_ids != running_modifier_ids:
            modifiers_changed = True

    # Force core restart if it's selected but modifiers changed. Tear down
    # synchronously (kills gz sim / RViz, not just the window) so the old sim is
    # gone before the new core launches.
    if modifiers_changed and core_pkg and core_pkg.selected:
         run_shell_command(CORE_TEARDOWN)
         save_state({"modifiers": []})
         core_pkg.is_running = False
         _pkg_start_times.pop('core', None)
         _intended_running.discard('core')
         for mod in state.packages:
             if mod.type == 'modifier':
                 if mod.is_running and 'stop' in mod.lifecycle_hooks:
                     run_shell_command(mod.lifecycle_hooks['stop'])
                 mod.is_running = False
                 _pkg_start_times.pop(mod.id, None)
                 _intended_running.discard(mod.id)

    # Display switch: if a VNC tool (display_switch package) is being toggled,
    # restart core first so GL apps open on the right DISPLAY after the virtual
    # desktop starts or stops. VNC tools are applied synchronously here so the
    # display is ready before core relaunches in the normal start pass below.
    display_switch_pkgs = [p for p in state.packages if p.display_switch]
    if any(p.selected != p.is_running for p in display_switch_pkgs):
        if core_pkg and core_pkg.is_running:
            run_shell_command(CORE_TEARDOWN)
            save_state({"modifiers": []})
            core_pkg.is_running = False
            _pkg_start_times.pop('core', None)
            _intended_running.discard('core')
            for mod in state.packages:
                if mod.type == 'modifier':
                    mod.is_running = False
                    _pkg_start_times.pop(mod.id, None)
                    _intended_running.discard(mod.id)
        for pkg in display_switch_pkgs:
            if pkg.selected and not pkg.is_running:
                run_shell_command(pkg.command['start'])
                pkg.is_running = True
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            elif not pkg.selected and pkg.is_running:
                run_shell_command(pkg.command['stop'])
                pkg.is_running = False
                _pkg_stop_times.pop(pkg.id, None)
                _pkg_start_times.pop(pkg.id, None)
                _intended_running.discard(pkg.id)

    # First Pass: Stop processes that should be turned off (or were forced off).
    # Stops run asynchronously so the TUI stays responsive and can show STOPPING
    # while a slow shutdown runs; the package leaves STOPPING once its probe reports
    # it gone. A modifier with no stop action is just marked stopped (its teardown
    # happens via the core restart above).
    for pkg in state.packages:
        if not pkg.selected and pkg.is_running:
            stopping = True
            if pkg.is_complex_command():
                run_shell_command_async(pkg.command['stop'])
            elif pkg.type == 'core':
                run_shell_command_async(CORE_TEARDOWN)
                save_state({"modifiers": []})
                for mod in state.packages:
                    if mod.type == 'modifier':
                        _pkg_start_times.pop(mod.id, None)
                        _intended_running.discard(mod.id)
            elif pkg.type in ['tool', 'interface']:
                run_shell_command_async(f"tmux kill-window -t lucy_ws:{pkg.id} 2>/dev/null")
            elif pkg.type == 'modifier' and 'stop' in pkg.lifecycle_hooks:
                run_shell_command_async(pkg.lifecycle_hooks['stop'])
            else:
                stopping = False
            _pkg_start_times.pop(pkg.id, None)
            _intended_running.discard(pkg.id)
            if stopping:
                _pkg_stop_times[pkg.id] = time.time()
            else:
                pkg.is_running = False

    # Second Pass: Start processes that should be turned on (never re-launch one
    # that is still shutting down). A crashed service (pane_dead) is relaunched
    # too, after reaping the dead window left open for debugging.
    for pkg in state.packages:
         if pkg.selected and pkg.id not in _pkg_stop_times and (not pkg.is_running or pkg.pane_dead):
            if pkg.pane_dead:
                run_shell_command(f"tmux kill-window -t lucy_ws:{pkg.id} 2>/dev/null")
                pkg.pane_dead = False
                pkg.is_running = False
            if pkg.is_complex_command():
                run_shell_command(pkg.command['start'])
                # Keep a crashed service's window open with its error (see core).
                if pkg.readiness_check:
                    run_shell_command(f"tmux set-window-option -t lucy_ws:{pkg.id} remain-on-exit on 2>/dev/null")
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            elif pkg.type == 'core':
                base_cmd = pkg.command
                selected_modifiers = [p for p in state.packages if p.type == 'modifier' and p.selected]
                modifier_args = [p.command for p in selected_modifiers]
                modifier_ids = [p.id for p in selected_modifiers]
                full_cmd = f"{base_cmd} {' '.join(modifier_args)}"
                # remain-on-exit keeps the window (and the crash output) open if
                # ros2 launch dies, so the failure is visible and detectable.
                run_shell_command(f"tmux new-window -d -t lucy_ws -n core '{full_cmd}'; tmux set-window-option -t lucy_ws:core remain-on-exit on")
                save_state({"modifiers": modifier_ids})
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
                for mod in selected_modifiers:
                    _pkg_start_times[mod.id] = time.time()
                    _intended_running.add(mod.id)
            elif pkg.type in ['tool', 'interface']:
                run_shell_command(f"tmux new-window -d -t lucy_ws -n {pkg.id} '{pkg.command}; echo \"--- Process finished, press any key to close ---\"; read'")
                # Don't auto-switch to GUI tools that render on the VNC desktop
                # (e.g. rqt) — their window is in the viewer, not this terminal.
                if not pkg.runs_on_vnc:
                    last_launched_window = pkg.id
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            pkg.is_running = True

    if last_launched_window:
        run_shell_command(f"tmux select-window -t lucy_ws:{last_launched_window}")

def restore_selection(state):
    """Pre-tick the packages the user last applied (persisted), so they don't have
    to re-select them after a restart. Running packages stay ticked regardless."""
    saved = load_selection()
    if saved is None:
        return
    robots = [p for p in state.packages if p.requires_pkg]
    for pkg in state.packages:
        if pkg.requires_pkg:
            continue
        pkg.selected = (pkg.id in saved) or pkg.is_running
    # Robot radios: at most one ticked (saved choice wins over stale is_running).
    chosen = next((p for p in robots if p.id in saved), None)
    if chosen is None:
        running = [p for p in robots if p.is_running]
        chosen = running[0] if len(running) == 1 else None
    for pkg in robots:
        pkg.selected = pkg is chosen

def default_robot_selection(state):
    """Auto-tick a robot-package modifier when none is selected yet (mirrors
    lucy.launch.py: sole installed robot, or inmoov_urdf when several are built).
    Gated on core being selected so it can be applied alongside core."""
    core = state.get_by_id('core')
    robots = [p for p in state.packages if p.requires_pkg]
    if not robots or not (core and core.selected):
        return
    if any(p.selected for p in robots):
        return
    if len(robots) == 1:
        robots[0].selected = True
        return
    inmoov = state.get_by_id('robot_inmoov')
    if inmoov:
        inmoov.selected = True

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(0) 
    stdscr.timeout(-1)
    curses.start_color()
    curses.use_default_colors()

    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_YELLOW, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)
        curses.init_pair(4, curses.COLOR_GREEN, -1)

    state = LauncherState(load_config())
    restore_selection(state)
    default_robot_selection(state)
    current_idx = 0
    error_msg = None
    status_msg = None
    status_msg_until = 0.0

    if not get_dev_mode():
        # Production: always ensure core + control panel, then start everything
        # selected (including any restored selection).
        core_pkg = state.get_by_id('core')
        lcp_pkg = state.get_by_id('control_panel')
        if core_pkg:
            core_pkg.selected = True
        if lcp_pkg:
            lcp_pkg.selected = True
        default_robot_selection(state)
        apply_changes(state)
        status_msg = "Starting default services for production mode..."
        state = LauncherState(load_config())
        restore_selection(state)

    while True:
        try:
            if status_msg and time.time() >= status_msg_until:
                status_msg = None
            display_list = draw_tui(stdscr, state, current_idx, error_msg, status_msg, _has_unapplied_changes(state))
            error_msg = None

            if display_list is None:
                # If display_list is None, it means the screen is too small.
                # We switch to non-blocking getch to poll for resize events
                stdscr.nodelay(1)
                stdscr.timeout(100)
                key = stdscr.getch()
                if key != curses.KEY_RESIZE:
                    time.sleep(0.1)
                continue
            else:
                # Poll fast while something is still coming up, slow once everything
                # we launched is up (so a later crash still surfaces), and block
                # entirely when nothing is running. Re-read state on each tick.
                if _pkg_start_times or _pkg_stop_times:
                    poll_ms = 1000
                elif _intended_running:
                    poll_ms = 5000
                else:
                    poll_ms = None
                if poll_ms is None:
                    stdscr.nodelay(0)
                    stdscr.timeout(-1)
                else:
                    stdscr.nodelay(1)
                    stdscr.timeout(poll_ms)
                key = stdscr.getch()
                if key == -1:
                    state.refresh_status()
                    continue

            if key == curses.KEY_RESIZE:
                continue

            if key == curses.KEY_UP:
                current_idx = (current_idx - 1) % len(display_list)
            elif key == curses.KEY_DOWN:
                current_idx = (current_idx + 1) % len(display_list)
            elif key == ord(' '):
                pkg_to_toggle = display_list[current_idx]
                error_msg = state.toggle(pkg_to_toggle.id)
            elif key == ord('\n'):
                apply_changes(state)
                save_selection({p.id for p in state.packages if p.selected})
                status_msg = "Configuration Applied!"
                status_msg_until = time.time() + 2.0
                state = LauncherState(load_config())
                restore_selection(state)
            elif key in [ord('x'), ord('X')]:
                h, w = stdscr.getmaxyx()
                stdscr.addstr(h - 2, 2, "Stop all processes and exit Docker? (y/n)", curses.A_BOLD | curses.color_pair(2))
                stdscr.refresh()
                confirm_key = stdscr.getch()
                if confirm_key in [ord('y'), ord('Y')]:
                    return "ExitWorkspace", state
            elif key in [ord('q'), ord('Q'), 27]:
                return "Quit", None
        
        except curses.error:
            # This will catch errors from addstr if the window is resized
            # between the size check and the drawing.
            time.sleep(0.1)
            continue

if __name__ == "__main__":
    if not is_in_docker() or not is_in_tmux():
        print("Error: This script must be run inside the 'lucy_ws' tmux session within the Docker container.", file=sys.stderr)
        sys.exit(1)

    status, state = None, None
    try:
        status, state = curses.wrapper(main)
    except Exception as e:
        # Clean up curses on any exception
        curses.endwin()
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if status == "ExitWorkspace":
        print("\nStopping all processes and exiting workspace...")
        if state:
            for pkg in state.packages:
                if pkg.is_complex_command():
                    run_shell_command(pkg.command['stop'])
                elif 'stop' in pkg.lifecycle_hooks:
                     run_shell_command(pkg.lifecycle_hooks['stop'])
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        print("Terminating tmux session...")
        time.sleep(0.5)
        run_shell_command("tmux kill-session -t lucy_ws 2>/dev/null")
    else:
        pass
