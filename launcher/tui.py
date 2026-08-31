"""Curses TUI rendering and main event loop."""

import time

try:
    import curses
except ImportError:
    curses = None

from .apply import apply_changes, default_robot_selection, restore_selection
from .config import get_dev_mode, load_config, save_selection
from .constants import MIN_TERM_HEIGHT, MIN_TERM_WIDTH
from .state import (
    LauncherState,
    _has_unapplied_changes,
    _intended_running,
    _nav_hint,
    _pkg_start_times,
    _pkg_stop_times,
    _status_url,
    get_pkg_status,
)


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
    if url and status == "running":
        text = f" ({url})"
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))
            col += len(text)
        except curses.error:
            pass
    if hint:
        text = f" {hint}"
        try:
            stdscr.addstr(y, col, text, curses.color_pair(3))
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
    stdscr.addstr(
        h - 1,
        2,
        "Enter: Apply | Space: Toggle | Q/X/Esc: Stop All & Exit",
        curses.A_BOLD,
    )

    if status_msg:
        stdscr.addstr(h - 2, 2, status_msg, curses.A_BOLD)
    elif error_msg:
        stdscr.addstr(h - 2, 2, f"Warning: {error_msg}", curses.color_pair(2))
    elif unapplied:
        stdscr.addstr(
            h - 2,
            2,
            "Unapplied changes — press Enter to apply",
            curses.color_pair(1),
        )

    robots = [p for p in state.packages if p.type == "modifier" and p.requires_pkg]
    cores_and_mods = [
        p for p in state.packages if p.type in ("core", "modifier") and not p.requires_pkg
    ]
    interfaces = [p for p in state.packages if p.type == "interface"]
    tools = [p for p in state.packages if p.type == "tool"]
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
            if p.type == "core":
                attr |= curses.A_BOLD
            if p.subitem:
                indent = "        "
            elif indent_all or p.type == "modifier":
                indent = "    "
            else:
                indent = ""
            status = get_pkg_status(p)
            hint = _nav_hint(p)
            _draw_pkg_row(
                stdscr,
                row + i,
                4,
                prefix,
                indent,
                checkbox,
                p.name,
                attr,
                status,
                hint,
                _status_url(p),
            )
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
        core_pkg = state.get_by_id("core")
        lcp_pkg = state.get_by_id("control_panel")
        if core_pkg:
            core_pkg.selected = True
        if lcp_pkg:
            lcp_pkg.selected = True
        default_robot_selection(state)
        apply_changes(state)
        save_selection({p.id for p in state.packages if p.selected})
        status_msg = "Starting default services for production mode..."
        status_msg_until = time.time() + 3.0
        state.refresh_status()

    while True:
        try:
            if status_msg and time.time() >= status_msg_until:
                status_msg = None
            display_list = draw_tui(
                stdscr,
                state,
                current_idx,
                error_msg,
                status_msg,
                _has_unapplied_changes(state),
            )
            error_msg = None

            if display_list is None:
                stdscr.nodelay(1)
                stdscr.timeout(100)
                key = stdscr.getch()
                if key != curses.KEY_RESIZE:
                    time.sleep(0.1)
                continue

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
            elif key == ord(" "):
                pkg_to_toggle = display_list[current_idx]
                error_msg = state.toggle(pkg_to_toggle.id)
            elif key == ord("\n"):
                apply_changes(state)
                save_selection({p.id for p in state.packages if p.selected})
                status_msg = "Configuration Applied!"
                status_msg_until = time.time() + 2.0
                state.refresh_status()
            elif key in [ord("x"), ord("X"), ord("q"), ord("Q"), 27]:
                h, w = stdscr.getmaxyx()
                stdscr.addstr(
                    h - 2,
                    2,
                    "Stop all processes and exit? (y/n)",
                    curses.A_BOLD | curses.color_pair(2),
                )
                stdscr.refresh()
                confirm_key = stdscr.getch()
                if confirm_key in [ord("y"), ord("Y")]:
                    return "ExitWorkspace", state

        except curses.error:
            time.sleep(0.1)
            continue
