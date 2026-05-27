#!/usr/bin/env python3

import curses
import os
import sys
import subprocess
import time

def is_in_docker():
    """Check if the script is running inside a Docker container."""
    return os.path.exists('/.dockerenv')

def is_cp_running():
    """Check if the Control Panel (Vite) is running."""
    result = subprocess.run("ps aux | grep '[v]ite'", shell=True, capture_output=True, text=True)
    return result.returncode == 0

def stop_cp():
    """Stop the Control Panel completely."""
    os.system("pkill -9 -f 'vite' > /dev/null 2>&1")
    time.sleep(0.5)

def main(stdscr):
    """Main function to run the TUI."""
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

    # Use lists instead of tuples so they are mutable
    options = [
        ["Core (Lucy Bringup)", "Base robot software stack", False, 'core'],
        ["... with Simulator", "(Gazebo)", False, 'modifier'],
        ["... with Visualizer", "(RViz)", False, 'modifier'],
        ["... with Real Hardware", "(Connect to physical robot)", False, 'modifier'],
        ["Control Panel", "Web-based UI (standalone)", is_cp_running(), 'standalone'],
        ["Lucy CLI", "Command Line Interface (standalone)", False, 'standalone'],
    ]
    current_option = 0

    while True:
        # --- Logic updates based on state ---
        core_selected = options[0][2]
        
        for i in range(1, 4): 
            if not core_selected:
                options[i][2] = False
        
        sim_selected = options[1][2]
        real_selected = options[3][2]

        # --- Drawing ---
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        title = "Lucy In-Container Launcher"
        stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
        stdscr.addstr(h - 1, 2, "Enter: Launch | Space: Toggle | Q: Quit", curses.A_DIM)

        stdscr.addstr(2, 2, "Primary Launch Target", curses.A_BOLD | curses.color_pair(1))
        
        prefix = "> " if current_option == 0 else "  "
        checkbox = "[x]" if options[0][2] else "[ ]"
        stdscr.addstr(4, 4, f"{prefix}{checkbox} {options[0][0]}", curses.A_BOLD)
        stdscr.addstr(4, 4 + len(prefix) + len(checkbox) + len(options[0][0]) + 1, f"- {options[0][1]}", curses.A_DIM)

        for i in range(1, 4):
            prefix = "> " if current_option == i else "  "
            checkbox = "[x]" if options[i][2] else "[ ]"
            line_attr = curses.A_NORMAL if core_selected else curses.A_DIM
            stdscr.addstr(5 + i, 6, f"{prefix}{checkbox} {options[i][0]}", line_attr)
            stdscr.addstr(5 + i, 6 + len(prefix) + len(checkbox) + len(options[i][0]) + 1, f"{options[i][1]}", line_attr | curses.A_DIM)

        stdscr.addstr(10, 2, "Standalone Tools", curses.A_BOLD | curses.color_pair(3))
        for i in range(4, 6):
            prefix = "> " if current_option == i else "  "
            checkbox = "[x]" if options[i][2] else "[ ]"
            stdscr.addstr(11 + (i - 4), 4, f"{prefix}{checkbox} {options[i][0]}", curses.A_NORMAL)
            stdscr.addstr(11 + (i - 4), 4 + len(prefix) + len(checkbox) + len(options[i][0]) + 1, f"- {options[i][1]}", curses.A_DIM)

        if sim_selected and real_selected:
             stdscr.addstr(h - 2, 2, "Warning: Simulator and Real Hardware are mutually exclusive.", curses.color_pair(2))

        stdscr.refresh()

        # --- Input Handling ---
        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_option = (current_option - 1) % len(options)
        elif key == curses.KEY_DOWN:
            current_option = (current_option + 1) % len(options)
        elif key == ord(' '):
            options[current_option][2] = not options[current_option][2]
            
            if current_option == 1 and options[1][2]:
                options[3][2] = False
            elif current_option == 3 and options[3][2]:
                options[1][2] = False
                
        elif key == ord('\n'):
            break
        elif key == ord('q') or key == ord('Q') or key == 27:
            return "Quit", None

    selections = [opt[2] for opt in options]
    return "Launch", selections


if __name__ == "__main__":
    if not is_in_docker():
        print("Error: This script must be run inside the Lucy Docker container.", file=sys.stderr)
        sys.exit(1)

    if not sys.stdout.isatty():
        print("Error: This TUI must be run in a terminal.", file=sys.stderr)
        sys.exit(1)

    try:
        status, message = curses.wrapper(main)
    except Exception as e:
        print(f"A terminal error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    if status == "Quit":
        print("No action taken.")
        sys.exit(0)
        
    if status == "Error":
        print(f"\nError: {message}", file=sys.stderr)
        sys.exit(1)

    if status == "Launch":
        core, sim, rviz, real, cp, cli = message
        
        cp_is_running = is_cp_running()
        if cp and not cp_is_running:
            print("Starting Control Panel...")
            subprocess.Popen(["yarn", "dev"], cwd="/workspace/src/lucy_control_panel", stdout=open("/tmp/lucy-cp.log", "w"), stderr=subprocess.STDOUT, preexec_fn=os.setpgrp)
        elif not cp and cp_is_running:
            print("Stopping Control Panel...")
            stop_cp()

        ros_cmd = ""
        if cli:
            if core:
                print("Warning: Lucy CLI is a standalone tool. Ignoring Core launch options.", file=sys.stderr)
            ros_cmd = "ros2 run lucy_cli tui"
        elif core:
            launch_args = []
            if sim:
                launch_args.append("gazebo:=true")
            if rviz:
                launch_args.append("rviz:=true")
            if real:
                launch_args.append("real:=true")
            ros_cmd = f"ros2 launch lucy_bringup lucy.launch.py {' '.join(launch_args)}"
        
        if ros_cmd:
            print(f"\nExecuting: {ros_cmd}")
            print("-" * 50)
            try:
                subprocess.run(ros_cmd, shell=True, check=True)
            except (subprocess.CalledProcessError, KeyboardInterrupt):
                print("\nCommand terminated.")
        else:
            print("\nNo primary target selected to launch.")
