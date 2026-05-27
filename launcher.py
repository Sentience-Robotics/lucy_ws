#!/usr/bin/env python3

import curses
import os
import sys
import subprocess
import time
import json

CONFIG_FILE = "/workspace/config/launcher_config.json"

def is_in_docker():
    return os.path.exists('/.dockerenv')

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file not found at {CONFIG_FILE}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing config file: {e}", file=sys.stderr)
            sys.exit(1)

def run_shell_command(cmd, capture_output=False):
    """Utility to run a shell command."""
    if capture_output:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0
    else:
        subprocess.run(cmd, shell=True)

class Package:
    def __init__(self, data):
        self.id = data['id']
        self.name = data['name']
        self.description = data.get('description', '')
        self.type = data['type']
        self.dependencies = data.get('dependencies', [])
        self.conflicts = data.get('conflicts', [])
        self.command = data.get('command', '')
        self.selected = data.get('default_on', False)
        
        # Determine initial state for complex standalone apps (like control panel)
        if isinstance(self.command, dict) and 'is_running' in self.command:
            self.selected = run_shell_command(self.command['is_running'], capture_output=True)

    def is_standalone_background(self):
        return isinstance(self.command, dict)

class LauncherState:
    def __init__(self, config_data):
        self.packages = [Package(p) for p in config_data['packages']]
        self.package_map = {p.id: p for p in self.packages}

    def get_by_id(self, pkg_id):
        return self.package_map.get(pkg_id)

    def toggle(self, pkg_id):
        pkg = self.get_by_id(pkg_id)
        if not pkg: return

        # If turning ON
        if not pkg.selected:
            # Check dependencies
            missing_deps = [dep for dep in pkg.dependencies if not self.get_by_id(dep).selected]
            if missing_deps:
                return f"Cannot enable '{pkg.name}'. Missing dependencies: {', '.join(missing_deps)}"

            # Resolve conflicts (turn off conflicting packages)
            for conflict_id in pkg.conflicts:
                conflict_pkg = self.get_by_id(conflict_id)
                if conflict_pkg and conflict_pkg.selected:
                    conflict_pkg.selected = False

            pkg.selected = True
        
        # If turning OFF
        else:
            # Turn off anything that depends on this
            for other_pkg in self.packages:
                if pkg_id in other_pkg.dependencies and other_pkg.selected:
                    other_pkg.selected = False
            
            pkg.selected = False
            
        return None # No error

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
    else:
        curses.init_pair(1, 0, 0)
        curses.init_pair(2, 0, 0)
        curses.init_pair(3, 0, 0)

    config_data = load_config()
    state = LauncherState(config_data)
    
    current_idx = 0
    error_msg = None

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Lucy Configurable Launcher"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
        stdscr.addstr(h - 1, 2, "Enter: Launch | Space: Toggle | Q: Quit", curses.A_DIM)

        if error_msg:
            stdscr.addstr(h - 2, 2, f"Warning: {error_msg}", curses.color_pair(2))
            error_msg = None # Clear after displaying once

        # Group packages for display
        cores_and_mods = [p for p in state.packages if p.type in ['core', 'modifier']]
        standalones = [p for p in state.packages if p.type == 'standalone']

        display_list = []
        
        row = 2
        stdscr.addstr(row, 2, "Primary Launch Targets", curses.A_BOLD | curses.color_pair(1))
        row += 2
        for p in cores_and_mods:
            display_list.append(p)
            prefix = "> " if current_idx == len(display_list) - 1 else "  "
            checkbox = "[x]" if p.selected else "[ ]"
            
            # Determine visual state based on dependencies
            can_enable = all(state.get_by_id(dep).selected for dep in p.dependencies)
            attr = curses.A_NORMAL if can_enable else curses.A_DIM
            if p.type == 'core': attr |= curses.A_BOLD
            
            indent = "    " if p.type == 'modifier' else ""
            stdscr.addstr(row, 4, f"{prefix}{indent}{checkbox} {p.name}", attr)
            stdscr.addstr(row, 4 + len(prefix) + len(indent) + len(checkbox) + len(p.name) + 1, f"- {p.description}", attr | curses.A_DIM)
            row += 1

        row += 1
        stdscr.addstr(row, 2, "Standalone Tools", curses.A_BOLD | curses.color_pair(3))
        row += 1
        for p in standalones:
            display_list.append(p)
            prefix = "> " if current_idx == len(display_list) - 1 else "  "
            checkbox = "[x]" if p.selected else "[ ]"
            stdscr.addstr(row, 4, f"{prefix}{checkbox} {p.name}", curses.A_NORMAL)
            stdscr.addstr(row, 4 + len(prefix) + len(checkbox) + len(p.name) + 1, f"- {p.description}", curses.A_DIM)
            row += 1

        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_idx = (current_idx - 1) % len(display_list)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(display_list)
        elif key == ord(' '):
            pkg_to_toggle = display_list[current_idx]
            err = state.toggle(pkg_to_toggle.id)
            if err:
                error_msg = err
        elif key == ord('\n'):
            break
        elif key == ord('q') or key == ord('Q') or key == 27:
            return "Quit", None

    return "Launch", state


if __name__ == "__main__":
    if not is_in_docker():
        print("Error: This script must be run inside the Lucy Docker container.", file=sys.stderr)
        sys.exit(1)

    if not sys.stdout.isatty():
        print("Error: This TUI must be run in a terminal.", file=sys.stderr)
        sys.exit(1)

    try:
        status, state = curses.wrapper(main)
    except Exception as e:
        print(f"A terminal error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if status == "Quit":
        print("No action taken.")
        sys.exit(0)

    if status == "Launch":
        # 1. Handle Background Standalones (like Control Panel)
        for pkg in state.packages:
            if pkg.is_standalone_background():
                was_running = run_shell_command(pkg.command['is_running'], capture_output=True)
                if pkg.selected and not was_running:
                    print(f"Starting {pkg.name}...")
                    # Using Popen to run in background
                    subprocess.Popen(
                        pkg.command['start'], 
                        shell=True, 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL, 
                        preexec_fn=os.setpgrp
                    )
                elif not pkg.selected and was_running:
                    print(f"Stopping {pkg.name}...")
                    run_shell_command(pkg.command['stop'])
                    time.sleep(0.5)

        # 2. Build Primary Execution Command
        core_pkg = next((p for p in state.packages if p.type == 'core' and p.selected), None)
        cli_pkg = next((p for p in state.packages if p.id == 'lucy_cli' and p.selected), None)
        
        final_cmd = ""
        
        if cli_pkg:
            final_cmd = cli_pkg.command
        elif core_pkg:
            base_cmd = core_pkg.command
            args = []
            for pkg in state.packages:
                if pkg.type == 'modifier' and pkg.selected and pkg.command:
                    args.append(pkg.command)
            final_cmd = f"{base_cmd} {' '.join(args)}"

        # 3. Execute
        if final_cmd:
            print(f"\nExecuting: {final_cmd}")
            print("-" * 50)
            try:
                subprocess.run(final_cmd, shell=True, check=True)
            except (subprocess.CalledProcessError, KeyboardInterrupt):
                print("\nCommand terminated.")
        else:
            print("\nConfiguration applied. No foreground command to execute.")
