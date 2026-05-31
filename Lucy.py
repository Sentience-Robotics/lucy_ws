#!/usr/bin/env python3

import curses
import os
import subprocess
import sys

def get_dev_mode():
    if not os.path.exists(".env"):
        return False
    with open(".env", "r") as f:
        for line in f:
            if line.strip().startswith("DEV="):
                return line.strip().split("=")[1].lower() == "true"
    return False

def set_dev_mode(is_enabled):
    lines = []
    dev_found = False
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()

    with open(".env", "w") as f:
        for line in lines:
            if line.strip().startswith("DEV="):
                f.write(f"DEV={str(is_enabled).lower()}\n")
                dev_found = True
            else:
                f.write(line)
        if not dev_found:
            f.write(f"DEV={str(is_enabled).lower()}\n")

def run_command(command, interactive=False):
    """Runs a command.
    
    If interactive is True, runs natively in the terminal.
    """
    print(f"--- Running: {' '.join(command)} ---")
    try:
        if interactive:
            # Inherit standard IO to maintain terminal size and TTY functionality 
            return subprocess.run(command).returncode
        else:
            # Popen is fine for non-interactive scripts like install/build
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(output.strip())
            return process.poll()

    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Make sure it's in your PATH and executable.")
        return -1
    except Exception as e:
        print(f"An error occurred: {e}")
        return -1

def main_tui(stdscr):
    """The main curses TUI function. Returns the command to run."""
    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)

    is_dev_mode = get_dev_mode()
    current_idx = 0
    options = ["Launch", "---", "Install/Update", "Rebuild", "Exit", "---", "Developer Mode"]

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Lucy Workspace Manager"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)

        for i, option in enumerate(options):
            if option == "---":
                stdscr.addstr(2 + i, 4, "----------------------")
                continue

            prefix = "> " if current_idx == i else "  "
            
            if option == "Developer Mode":
                checkbox = "[x]" if is_dev_mode else "[ ]"
                stdscr.addstr(2 + i, 4, f"{prefix}{checkbox} {option}")
            else:
                stdscr.addstr(2 + i, 4, f"{prefix}{option}")

        stdscr.addstr(h - 2, 2, "Enter/Space: Select/Toggle | Up/Down: Navigate", curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_idx = (current_idx - 1 + len(options)) % len(options)
            if options[current_idx] == "---":
                current_idx = (current_idx - 1 + len(options)) % len(options)
        elif key == curses.KEY_DOWN:
            current_idx = (current_idx + 1) % len(options)
            if options[current_idx] == "---":
                current_idx = (current_idx + 1) % len(options)
        elif key in [ord(' '), ord('\n')]:
            selected_option = options[current_idx]

            if selected_option == "Developer Mode":
                is_dev_mode = not is_dev_mode
                set_dev_mode(is_dev_mode)
            elif selected_option == "Install/Update":
                return {"cmd": ["./install.sh"], "interactive": False, "name": "Install"}
            elif selected_option == "Rebuild":
                return {"cmd": ["./install.sh", "--build-only"], "interactive": False, "name": "Rebuild"}
            elif selected_option == "Launch":
                return {"cmd": ["./launch_lucy.sh"], "interactive": True, "name": "Launch"}
            elif selected_option == "Exit":
                return None

if __name__ == "__main__":
    while True:
        task = None
        try:
            # curses.wrapper handles all the init/deinit of the terminal
            task = curses.wrapper(main_tui)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)

        if not task:
            # User selected Exit
            break

        rc = run_command(task["cmd"], interactive=task.get("interactive", False))

        if task.get("interactive", False):
            # For interactive tasks like "Launch", when they finish, we exit the manager.
            print(f"--- Session finished with exit code {rc} ---")
            break
        
        # For non-interactive tasks
        task_name = task.get("name")
        if task_name in ["Install", "Rebuild"] and rc == 0:
            print(f"\n--- Task '{task_name}' finished successfully. ---")
            print("Press Enter to return to the menu.")
            input()
            # Loop back to show the TUI again
        else:
            print(f"\n--- Task '{task_name}' finished with exit code {rc} ---")
            print("Press Enter to exit.")
            input()
            break

    sys.exit(0)
