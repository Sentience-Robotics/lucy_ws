"""Curses TUI rendering and main event loop.

Cross-platform notes
---------------------
The stdlib `curses` module does not exist on Windows. To run this file on
Windows you need the `windows-curses` package installed (it provides a
drop-in `_curses`/`curses` implementation backed by PDCurses), e.g.:

    pip install windows-curses

If it isn't installed, `curses` will be `None` and `main()` will print a
helpful message instead of crashing with an AttributeError.

A few PDCurses (Windows) quirks are also handled explicitly:
  * `use_default_colors()` / transparent (-1) backgrounds aren't reliably
    supported on every Windows console, so we fall back to COLOR_BLACK.
  * PDCurses does not reliably deliver KEY_RESIZE while `getch()` is
    blocked indefinitely (no SIGWINCH on Windows), so on Windows we never
    block forever - we poll on a short timeout instead.
  * Writing to the terminal's bottom-right cell raises curses.error on
    some consoles (this is stricter on Windows). All screen writes go
    through `_safe_addstr`, which clips to the screen bounds and
    swallows that specific error instead of aborting the whole frame.
"""

import sys
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

IS_WINDOWS = sys.platform.startswith("win")

# On Windows, don't ever block on getch() indefinitely: PDCurses doesn't
# reliably surface KEY_RESIZE (or console-resize at all) while blocked,
# so we poll on a short timeout instead to stay responsive.
WINDOWS_IDLE_POLL_MS = 1000


def _safe_addstr(stdscr, y, x, text, attr=0):
    """addstr that clips to the screen bounds and never raises curses.error.

    Windows consoles (PDCurses) are stricter than most Unix terminals about
    writing into the last cell of the screen, so this keeps drawing
    resilient across platforms instead of aborting the whole frame.
    """
    if not text:
        return x
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return x
    max_len = w - x
    if IS_WINDOWS and y == h - 1:
        # Avoid writing into the bottom-right cell, which some Windows
        # consoles refuse even with clipping.
        max_len -= 1
    clipped = text[: max(0, max_len)]
    try:
        stdscr.addstr(y, x, clipped, attr)
    except curses.error:
        pass
    return x + len(clipped)


def _draw_pkg_row(stdscr, y, x, prefix, indent, checkbox, name, attr, status, hint="", url=""):
    base = f"{prefix}{indent}{checkbox} {name}"
    col = _safe_addstr(stdscr, y, x, base, attr)
    labels = {
        "running": (" [RUNNING]", curses.color_pair(4)),
        "loading": (" [LOADING]", curses.color_pair(1)),
        "stopping": (" [STOPPING]", curses.color_pair(1)),
        "crashed": (" [CRASHED]", curses.color_pair(2) | curses.A_BOLD),
        "stopped": (" [STOPPED]", curses.A_DIM),
    }
    status_str, status_attr = labels.get(status, (" [STOPPED]", curses.A_DIM))
    col = _safe_addstr(stdscr, y, col, status_str, status_attr)
    if url and status == "running":
        col = _safe_addstr(stdscr, y, col, f" ({url})", curses.color_pair(3))
    if hint:
        col = _safe_addstr(stdscr, y, col, f" {hint}", curses.color_pair(3))


def draw_too_small_message(stdscr):
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    message = "Please increase terminal size"
    message2 = f"({MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT} required)"
    _safe_addstr(stdscr, h // 2 - 1, max(0, (w - len(message)) // 2), message, curses.A_BOLD)
    _safe_addstr(stdscr, h // 2, max(0, (w - len(message2)) // 2), message2, curses.A_DIM)
    stdscr.refresh()


def draw_tui(stdscr, state, current_idx, error_msg, status_msg, unapplied=False):
    h, w = stdscr.getmaxyx()
    if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
        draw_too_small_message(stdscr)
        return None

    stdscr.clear()
    title = "Lucy Control Center"
    _safe_addstr(stdscr, 0, max(0, (w - len(title)) // 2), title, curses.A_BOLD)
    _safe_addstr(
        stdscr,
        h - 1,
        2,
        "Enter: Apply | Space: Toggle | Q/X/Esc: Stop All & Exit",
        curses.A_BOLD,
    )

    if status_msg:
        _safe_addstr(stdscr, h - 2, 2, status_msg, curses.A_BOLD)
    elif error_msg:
        _safe_addstr(stdscr, h - 2, 2, f"Warning: {error_msg}", curses.color_pair(2))
    elif unapplied:
        _safe_addstr(
            stdscr,
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
        _safe_addstr(stdscr, row, 2, title, curses.A_BOLD | color)
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


def _init_colors():
    """Set up color pairs, tolerating consoles that reject default (-1) colors.

    Some Windows consoles (older cmd.exe / legacy PDCurses backends) don't
    support `use_default_colors()` / transparent backgrounds the way most
    Unix terminals do. Fall back to explicit COLOR_BLACK backgrounds.
    """
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except curses.error:
        bg = curses.COLOR_BLACK
    curses.init_pair(1, curses.COLOR_YELLOW, bg)
    curses.init_pair(2, curses.COLOR_RED, bg)
    curses.init_pair(3, curses.COLOR_CYAN, bg)
    curses.init_pair(4, curses.COLOR_GREEN, bg)


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(0)
    stdscr.timeout(-1)

    _init_colors()

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
                if IS_WINDOWS:
                    # PDCurses doesn't reliably deliver KEY_RESIZE (or any
                    # console-resize notification) while getch() is
                    # blocked indefinitely, since Windows has no SIGWINCH.
                    # Poll on a short timeout instead so resizes and
                    # status refreshes still get picked up.
                    stdscr.nodelay(1)
                    stdscr.timeout(WINDOWS_IDLE_POLL_MS)
                else:
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
                _safe_addstr(
                    stdscr,
                    h - 2,
                    2,
                    "Stop all processes and exit? (y/n)",
                    curses.A_BOLD | curses.color_pair(2),
                )
                stdscr.refresh()
                # Make sure the confirmation prompt actually waits for a
                # keypress rather than inheriting a non-blocking timeout
                # from the polling above (important on Windows, where
                # nodelay(1) getch() can spuriously return -1 immediately).
                stdscr.nodelay(0)
                stdscr.timeout(-1)
                confirm_key = stdscr.getch()
                if confirm_key in [ord("y"), ord("Y")]:
                    return "ExitWorkspace", state

        except curses.error:
            time.sleep(0.1)
            continue


def run():
    """Entry point that also handles the "curses isn't installed" case.

    On Windows, `curses` will be `None` if the `windows-curses` package
    isn't installed. Rather than letting `curses.wrapper` raise an
    AttributeError, print an actionable message.
    """
    if curses is None:
        if IS_WINDOWS:
            print(
                "This TUI requires the 'windows-curses' package on Windows.\n"
                "Install it with:  pip install windows-curses"
            )
        else:
            print("This TUI requires the standard library 'curses' module, "
                  "which is unavailable in this environment.")
        return None
    return curses.wrapper(main)


if __name__ == "__main__":
    run()