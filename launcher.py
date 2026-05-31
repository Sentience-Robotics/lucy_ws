#!/usr/bin/env python3

import curses
import os
import sys
import subprocess
import time
import json

CONFIG_FILE = "/workspace/config/launcher_config.json"
STATE_FILE = "/tmp/launcher_state.json"
MIN_TERM_HEIGHT = 22
MIN_TERM_WIDTH = 65

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

        self.update_running_status(running_modifiers)

    def update_running_status(self, running_modifiers):
        if self.is_complex_command():
            self.selected = run_shell_command(self.command['is_running'], capture_output=True)
        elif self.type == 'modifier':
            self.selected = self.id in running_modifiers
        elif self.type == 'core':
            self.selected = run_shell_command(f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'", capture_output=True)
            if not self.selected:
                save_state({"modifiers": []})
        elif self.type in ['tool', 'interface']:
             self.selected = run_shell_command(f"tmux list-windows -F '#{{window_name}}' | grep -q '^{self.id}$'", capture_output=True)

    def is_complex_command(self):
        return isinstance(self.command, dict)

class LauncherState:
    def __init__(self, config_data):
        running_state = load_state()
        self.packages = [Package(p, running_state['modifiers']) for p in config_data['packages']]
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

def draw_tui(stdscr, state, current_idx, error_msg, status_msg):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
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
        stdscr.addstr(row + i, 4, f"{prefix}{indent}{checkbox} {p.name}", attr)

    row += len(cores_and_mods) + 1
    stdscr.addstr(row, 2, "Interfaces", curses.A_BOLD | curses.color_pair(3))
    row += 1
    for i, p in enumerate(interfaces):
        list_idx = i + len(cores_and_mods)
        prefix = "> " if current_idx == list_idx else "  "
        checkbox = "[x]" if p.selected else "[ ]"
        stdscr.addstr(row + i, 4, f"{prefix}{checkbox} {p.name}", curses.A_NORMAL)

    row += len(interfaces) + 1
    stdscr.addstr(row, 2, "Tools", curses.A_BOLD | curses.color_pair(3))
    row += 1
    for i, p in enumerate(tools):
        list_idx = i + len(cores_and_mods) + len(interfaces)
        prefix = "> " if current_idx == list_idx else "  "
        checkbox = "[x]" if p.selected else "[ ]"
        stdscr.addstr(row + i, 4, f"{prefix}{checkbox} {p.name}", curses.A_NORMAL)

    stdscr.refresh()
    return display_list

def apply_changes(state):
    last_launched_window = None

    # First Pass: Stop processes that should be turned off
    for pkg in state.packages:
        if pkg.is_complex_command():
            was_running = run_shell_command(pkg.command['is_running'], capture_output=True)
            if not pkg.selected and was_running:
                run_shell_command(pkg.command['stop'])
        elif pkg.type == 'modifier':
             if not pkg.selected and 'stop' in pkg.lifecycle_hooks:
                  run_shell_command(pkg.lifecycle_hooks['stop'])

        elif pkg.type == 'core' and not pkg.selected:
             run_shell_command("tmux kill-window -t lucy_ws:core 2>/dev/null")
             save_state({"modifiers": []})
        elif pkg.type in ['tool', 'interface'] and not pkg.selected:
            run_shell_command(f"tmux kill-window -t lucy_ws:{pkg.id} 2>/dev/null")

    # Second Pass: Start processes that should be turned on
    for pkg in state.packages:
         if pkg.is_complex_command():
            was_running = run_shell_command(pkg.command['is_running'], capture_output=True)
            if pkg.selected and not was_running:
                run_shell_command(pkg.command['start'])
         elif pkg.type == 'core' and pkg.selected:
                run_shell_command("tmux kill-window -t lucy_ws:core 2>/dev/null")
                base_cmd = pkg.command
                selected_modifiers = [p for p in state.packages if p.type == 'modifier' and p.selected]
                modifier_args = [p.command for p in selected_modifiers]
                modifier_ids = [p.id for p in selected_modifiers]
                full_cmd = f"{base_cmd} {' '.join(modifier_args)}"
                run_shell_command(f"tmux new-window -d -t lucy_ws -n core '{full_cmd}; echo \"--- Process finished, press any key to close ---\"; read'")
                save_state({"modifiers": modifier_ids})
         elif pkg.type in ['tool', 'interface'] and pkg.selected:
            run_shell_command(f"tmux kill-window -t lucy_ws:{pkg.id} 2>/dev/null")
            run_shell_command(f"tmux new-window -d -t lucy_ws -n {pkg.id} '{pkg.command}; echo \"--- Process finished, press any key to close ---\"; read'")
            last_launched_window = pkg.id

    if last_launched_window:
        run_shell_command(f"tmux select-window -t lucy_ws:{last_launched_window}")

def main(stdscr):
    h, w = stdscr.getmaxyx()
    if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
        return "TerminalTooSmall", None

    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    curses.start_color()
    curses.use_default_colors()

    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_YELLOW, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        curses.init_pair(3, curses.COLOR_CYAN, -1)

    state = LauncherState(load_config())
    current_idx = 0
    error_msg = None
    status_msg = None

    # On first launch in production mode, start default services
    if not get_dev_mode():
        core_pkg = state.get_by_id('core')
        cp_pkg = state.get_by_id('control_panel')
        
        should_apply_defaults = False
        if core_pkg and not core_pkg.selected:
            core_pkg.selected = True
            should_apply_defaults = True
        if cp_pkg and not cp_pkg.selected:
            cp_pkg.selected = True
            should_apply_defaults = True

        if should_apply_defaults:
            apply_changes(state)
            status_msg = "Starting default services for production mode..."
            # Reload state to reflect that services are now running
            state = LauncherState(load_config())


    while True:
        display_list = draw_tui(stdscr, state, current_idx, error_msg, status_msg)
        error_msg = None
        status_msg = None # Reset status message after one display

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_idx = (current_idx - 1) % len(display_list)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(display_list)
        elif key == ord(' '):
            pkg_to_toggle = display_list[current_idx]
            error_msg = state.toggle(pkg_to_toggle.id)
        elif key == ord('\n'):
            apply_changes(state)
            status_msg = "Configuration Applied!"
            # Reload state to get the latest running status
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

if __name__ == "__main__":
    if not is_in_docker() or not is_in_tmux():
        print("Error: This script must be run inside the 'lucy_ws' tmux session within the Docker container.", file=sys.stderr)
        sys.exit(1)

    status, state = None, None
    try:
        status, state = curses.wrapper(main)
    except curses.error as e:
        print(f"A terminal error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if status == "ExitWorkspace":
        print("\nStopping all processes and exiting workspace...")
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
    elif status == "TerminalTooSmall":
        print("Error: Terminal window is too small.", file=sys.stderr)
        print(f"Please increase the terminal size to at least {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} characters.", file=sys.stderr)
        print("Alternatively, use the underlying shell scripts (install.sh, launch_lucy.sh).", file=sys.stderr)
        print("\nPress any key to exit this session.", file=sys.stderr)
        # Wait for a key press before exiting
        curses.cbreak()
        curses.noecho()
        sys.stdin.read(1)
        # Cleanly exit the tmux session
        run_shell_command("tmux kill-session -t lucy_ws 2>/dev/null")
        sys.exit(1)
    else:
        # For "Quit" or other cases, just exit gracefully
        pass
