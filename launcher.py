#!/usr/bin/env python3

import curses
import os
import sys
import subprocess
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

_pkg_start_times = {}   # pkg_id -> float, timestamp when start was issued
_intended_running = set()  # pkg_ids that should be running (for crash detection)

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
        # Optional shell probe that exits 0 only once the package is truly up.
        # Without it, a package is considered "ready" the instant its window exists.
        self.readiness_check = data.get('readiness_check')
        self.readiness_timeout = data.get('readiness_timeout', LOADING_TIMEOUT)

        # is_running = window/process exists; ready = readiness probe passed.
        self.is_running = False
        self.ready = False
        self.update_running_status(running_modifiers)
        
        # Initialize selected state to match running state initially
        if self.is_running:
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

def _pkg_visible(pkg_config, dev_mode):
    """Whether a package appears in the launcher: hidden when it is `dev_only` and
    Developer Mode is off, or when its `requires_env` gate isn't satisfied."""
    if pkg_config.get('dev_only') and not dev_mode:
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

    def toggle(self, pkg_id):
        pkg = self.get_by_id(pkg_id)
        if not pkg: return None
        if not pkg.selected:
            missing_deps = [dep for dep in pkg.dependencies if not self.get_by_id(dep).selected]
            if missing_deps:
                return f"Needs: {', '.join(missing_deps)}"
            for conflict_id in pkg.conflicts:
                conflict_pkg = self.get_by_id(conflict_id)
                if conflict_pkg and conflict_pkg.selected:
                    conflict_pkg.selected = False
            pkg.selected = True
        else:
            for other_pkg in self.packages:
                if pkg_id in other_pkg.dependencies and other_pkg.selected:
                    other_pkg.selected = False
            pkg.selected = False
        return None

def get_pkg_status(pkg):
    """Return one of: running, loading, crashed, stopped.

    ``pkg.is_running`` means the tmux window / process merely exists; ``pkg.ready``
    means its readiness probe passed (the stack is actually up). A package we
    started (in ``_intended_running``) that isn't ready yet shows LOADING until its
    timeout elapses, after which it is reported CRASHED.
    """
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

def _draw_pkg_row(stdscr, y, x, prefix, indent, checkbox, name, attr, status):
    base = f"{prefix}{indent}{checkbox} {name}"
    stdscr.addstr(y, x, base, attr)
    labels = {
        "running": (" [RUNNING]", curses.color_pair(4)),
        "loading": (" [LOADING]", curses.color_pair(1)),
        "crashed": (" [CRASHED]", curses.color_pair(2) | curses.A_BOLD),
        "stopped": (" [STOPPED]", curses.A_DIM),
    }
    status_str, status_attr = labels.get(status, (" [STOPPED]", curses.A_DIM))
    try:
        stdscr.addstr(y, x + len(base), status_str, status_attr)
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

def draw_tui(stdscr, state, current_idx, error_msg, status_msg):
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

    cores_and_mods = [p for p in state.packages if p.type in ['core', 'modifier']]
    interfaces = [p for p in state.packages if p.type == 'interface']
    tools = [p for p in state.packages if p.type == 'tool']
    display_list = cores_and_mods + interfaces + tools

    row = 2
    stdscr.addstr(row, 2, "Primary Launch Targets", curses.A_BOLD | curses.color_pair(1))
    row += 2
    for i, p in enumerate(cores_and_mods):
        prefix = "> " if current_idx == i else "  "
        checkbox = "[x]" if p.selected else "[ ]"
        can_enable = all(state.get_by_id(dep).selected for dep in p.dependencies)
        attr = curses.A_NORMAL if can_enable else curses.A_DIM
        if p.type == 'core': attr |= curses.A_BOLD
        indent = "    " if p.type == 'modifier' else ""
        status = get_pkg_status(p)
        _draw_pkg_row(stdscr, row + i, 4, prefix, indent, checkbox, p.name, attr, status)

    row += len(cores_and_mods) + 1
    stdscr.addstr(row, 2, "Interfaces", curses.A_BOLD | curses.color_pair(3))
    row += 1
    for i, p in enumerate(interfaces):
        list_idx = i + len(cores_and_mods)
        prefix = "> " if current_idx == list_idx else "  "
        checkbox = "[x]" if p.selected else "[ ]"
        status = get_pkg_status(p)
        _draw_pkg_row(stdscr, row + i, 4, prefix, "", checkbox, p.name, curses.A_NORMAL, status)

    row += len(interfaces) + 1
    stdscr.addstr(row, 2, "Tools", curses.A_BOLD | curses.color_pair(3))
    row += 1
    for i, p in enumerate(tools):
        list_idx = i + len(cores_and_mods) + len(interfaces)
        prefix = "> " if current_idx == list_idx else "  "
        checkbox = "[x]" if p.selected else "[ ]"
        status = get_pkg_status(p)
        _draw_pkg_row(stdscr, row + i, 4, prefix, "", checkbox, p.name, curses.A_NORMAL, status)

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

    # Force core restart if it's selected but modifiers changed
    if modifiers_changed and core_pkg and core_pkg.selected:
         run_shell_command("tmux kill-window -t lucy_ws:core 2>/dev/null")
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

    # First Pass: Stop processes that should be turned off (or were forced off)
    for pkg in state.packages:
        if not pkg.selected and pkg.is_running:
            if pkg.is_complex_command():
                run_shell_command(pkg.command['stop'])
            elif pkg.type == 'modifier' and 'stop' in pkg.lifecycle_hooks:
                run_shell_command(pkg.lifecycle_hooks['stop'])
            elif pkg.type == 'core':
                run_shell_command("tmux kill-window -t lucy_ws:core 2>/dev/null")
                save_state({"modifiers": []})
                for mod in state.packages:
                    if mod.type == 'modifier':
                        _pkg_start_times.pop(mod.id, None)
                        _intended_running.discard(mod.id)
            elif pkg.type in ['tool', 'interface']:
                run_shell_command(f"tmux kill-window -t lucy_ws:{pkg.id} 2>/dev/null")
            _pkg_start_times.pop(pkg.id, None)
            _intended_running.discard(pkg.id)
            pkg.is_running = False

    # Second Pass: Start processes that should be turned on
    for pkg in state.packages:
         if pkg.selected and not pkg.is_running:
            if pkg.is_complex_command():
                run_shell_command(pkg.command['start'])
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
            elif pkg.type == 'core':
                base_cmd = pkg.command
                selected_modifiers = [p for p in state.packages if p.type == 'modifier' and p.selected]
                modifier_args = [p.command for p in selected_modifiers]
                modifier_ids = [p.id for p in selected_modifiers]
                full_cmd = f"{base_cmd} {' '.join(modifier_args)}"
                run_shell_command(f"tmux new-window -d -t lucy_ws -n core '{full_cmd}; echo \"--- Process finished, press any key to close ---\"; read'")
                save_state({"modifiers": modifier_ids})
                _pkg_start_times[pkg.id] = time.time()
                _intended_running.add(pkg.id)
                for mod in selected_modifiers:
                    _pkg_start_times[mod.id] = time.time()
                    _intended_running.add(mod.id)
            elif pkg.type in ['tool', 'interface']:
                run_shell_command(f"tmux new-window -d -t lucy_ws -n {pkg.id} '{pkg.command}; echo \"--- Process finished, press any key to close ---\"; read'")
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
    for pkg in state.packages:
        pkg.selected = (pkg.id in saved) or pkg.is_running

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
    current_idx = 0
    error_msg = None
    status_msg = None

    if not get_dev_mode():
        # Production: always ensure core + control panel, then start everything
        # selected (including any restored selection).
        core_pkg = state.get_by_id('core')
        cp_pkg = state.get_by_id('control_panel')
        if core_pkg:
            core_pkg.selected = True
        if cp_pkg:
            cp_pkg.selected = True
        apply_changes(state)
        status_msg = "Starting default services for production mode..."
        state = LauncherState(load_config())

    while True:
        try:
            display_list = draw_tui(stdscr, state, current_idx, error_msg, status_msg)
            error_msg = None
            status_msg = None 

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
                if _pkg_start_times:
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
                    state = LauncherState(load_config())
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
                state = LauncherState(load_config())
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
