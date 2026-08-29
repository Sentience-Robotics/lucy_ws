#!/usr/bin/env python3

import curses
import os
import subprocess
import sys
import shutil

MIN_TERM_HEIGHT = 15
MIN_TERM_WIDTH = 65

def is_installed():
    """True when the workspace has been built (mirrors launch_lucy.sh's check)."""
    return os.path.isfile("install/setup.bash")

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

def check_prereqs():
    if shutil.which("pixi") is None:
        print("Missing pixi. Install: https://pixi.prefix.dev/latest/installation/")
        return False
    return True

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

def not_installed_screen(stdscr):
    """First-run screen shown when the workspace isn't built yet.
    Returns True to install, False to close. (Terminal size is guaranteed by the
    pre-check in __main__.)"""
    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)

    is_dev_mode = get_dev_mode()

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Lucy Workspace Manager"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)

        lines = [
            ("Lucy is not installed on this machine.", curses.A_BOLD),
            ("", curses.A_NORMAL),
        ]
        start = max(2, h // 2 - len(lines) // 2)
        for i, (text, attr) in enumerate(lines):
            stdscr.addstr(start + i, max(0, (w - len(text)) // 2), text, attr)

        checkbox = "[x]" if is_dev_mode else "[ ]"
        dev_line = f"{checkbox} Developer Mode"
        stdscr.addstr(start + len(lines), max(0, (w - len(dev_line)) // 2), dev_line)
        hint_line = "(SSH clones during install; does not change Launch)"
        stdscr.addstr(start + len(lines) + 1, max(0, (w - len(hint_line)) // 2), hint_line, curses.A_DIM)

        footer = [
            ("", curses.A_NORMAL),
            ("Press ENTER to install", curses.A_NORMAL),
            ("Press Q or ESC to close", curses.A_DIM),
        ]
        for i, (text, attr) in enumerate(footer):
            stdscr.addstr(start + len(lines) + 3 + i, max(0, (w - len(text)) // 2), text, attr)

        stdscr.addstr(h - 2, 2, "Space: Toggle Developer Mode", curses.A_DIM)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord('\n'), ord('\r')):
            set_dev_mode(is_dev_mode)
            return True
        if key in (ord('q'), ord('Q'), 27):  # q / ESC
            return False
        if key == ord(' '):
            is_dev_mode = not is_dev_mode
            set_dev_mode(is_dev_mode)

def main_tui(stdscr):
    """The main curses TUI function. Returns the command to run."""
    h, w = stdscr.getmaxyx()
    if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
        return "TerminalTooSmall"

    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)

    is_dev_mode = get_dev_mode()
    current_idx = 0
    options = ["Launch", "---", "Update", "Rebuild", "Exit", "---", "Developer Mode"]

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

        stdscr.addstr(h - 2, 2, "Or: pixi run build, ./launch_lucy.sh", curses.A_DIM)
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
            elif selected_option == "Update":
                return {"cmd": ["./install.sh"], "interactive": False, "name": "Install"}
            elif selected_option == "Rebuild":
                return {
                    "cmd": ["pixi", "run", "build"],
                    "interactive": False,
                    "name": "Rebuild",
                    "followup": [["pixi", "run", "panel-install"]],
                }
            elif selected_option == "Launch":
                return {"cmd": ["./launch_lucy.sh"], "interactive": True, "name": "Launch"}
            elif selected_option == "Exit":
                return None

if __name__ == "__main__":
    # This initial check is done before curses.wrapper to provide a clean error message
    # without the screen flicker of initializing and de-initializing curses.
    def check_initial_size():
        stdscr = curses.initscr()
        h, w = stdscr.getmaxyx()
        curses.endwin()
        return h >= MIN_TERM_HEIGHT and w >= MIN_TERM_WIDTH

    if not check_initial_size():
        print("Error: Terminal window is too small.", file=sys.stderr)
        print(f"Please increase the terminal size to at least {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} characters.", file=sys.stderr)
        sys.exit(1)

    if not check_prereqs():
        sys.exit(1)

    # First run: nothing built yet — offer to install before showing the menu.
    if not is_installed():
        try:
            wants_install = curses.wrapper(not_installed_screen)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        except curses.error as e:
            print(f"A terminal error occurred: {e}", file=sys.stderr)
            print("This might be due to resizing the window. Please restart.", file=sys.stderr)
            sys.exit(1)
        if not wants_install:
            sys.exit(0)
        rc = run_command(["./install.sh"], interactive=False)
        if rc != 0:
            print(f"\n--- Install finished with exit code {rc} ---")
            print("Press Enter to exit.")
            input()
            sys.exit(rc)
        print("\n--- Install finished successfully. ---")
        print("Press Enter to continue to the menu.")
        input()

    while True:
        task = None
        try:
            task = curses.wrapper(main_tui)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        except curses.error as e:
            print(f"A terminal error occurred: {e}", file=sys.stderr)
            print("This might be due to resizing the window. Please restart.", file=sys.stderr)
            sys.exit(1)

        if isinstance(task, str) and task == "TerminalTooSmall":
             # This case is handled by the pre-check, but as a fallback.
            print("Error: Terminal window is too small.", file=sys.stderr)
            print(f"Please increase the terminal size to at least {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} characters.", file=sys.stderr)
            sys.exit(1)

        if not task:
            # User selected Exit
            break

        rc = run_command(task["cmd"], interactive=task.get("interactive", False))
        for follow in task.get("followup", []):
            if rc != 0:
                break
            rc = run_command(follow, interactive=False)

        if task.get("interactive", False):
            print(f"--- Session finished with exit code {rc} ---")
            break

        task_name = task.get("name")
        if task_name in ["Install", "Rebuild"] and rc == 0:
            print(f"\n--- Task '{task_name}' finished successfully. ---")
            print("Press Enter to return to the menu.")
            input()
        else:
            print(f"\n--- Task '{task_name}' finished with exit code {rc} ---")
            print("Press Enter to exit.")
            input()
            break

    sys.exit(0)
