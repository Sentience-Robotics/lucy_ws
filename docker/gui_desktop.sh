#!/usr/bin/env bash
# Self-contained virtual desktop for GUI apps that need OpenGL (RViz, Gazebo).
#
# Runs entirely inside the container: an Xvfb display rendered by Mesa llvmpipe
# (software GL) plus a small window manager (the "display"), and on top of it a
# password-protected VNC server and/or a passwordless noVNC (browser) endpoint.
# Used where the host X server can't give the container an OpenGL/GLX context —
# notably macOS XQuartz, where RViz/Gazebo otherwise fail to create a GLXContext.
#
# Components are controlled independently:
#   gui_desktop.sh display start|stop|status   # Xvfb + window manager (the monitor)
#   gui_desktop.sh vnc     start|stop|status   # native VNC server  (localhost:5901, password)
#   gui_desktop.sh novnc   start|stop|status   # browser viewer     (http://localhost:6080)
#   gui_desktop.sh start|stop                  # all of the above (back-compat)
#
# launch_lucy.sh auto-starts the display on macOS before tmux; the VNC and noVNC
# endpoints are toggled as interfaces from the Lucy Control Center launcher.
set -u

DISPLAY_NUM="${LUCY_GUI_DISPLAY_NUM:-99}"
GEOMETRY="${LUCY_GUI_GEOMETRY:-1600x900}"
DEPTH=24
VNC_PORT="${LUCY_GUI_VNC_PORT:-5901}"
NOVNC_PORT="${LUCY_GUI_NOVNC_PORT:-6080}"
NOVNC_VNC_PORT="${LUCY_GUI_NOVNC_VNC_PORT:-5902}"
# Native VNC clients (macOS Screen Sharing, RealVNC Viewer) refuse a no-auth
# server, so the native VNC endpoint is password-protected. The VNC auth scheme
# only uses the first 8 characters. Override with LUCY_GUI_VNC_PASSWORD.
VNC_PASSWORD="${LUCY_GUI_VNC_PASSWORD:-lucy}"
VNC_PASSWD_FILE=/tmp/.lucy_vncpasswd
export DISPLAY=":${DISPLAY_NUM}"

log() { echo "[gui_desktop] $*"; }
# Match by exact process name (comm), not full command line, so these checks can't
# accidentally match the surrounding shell whose argv may mention these binaries.
proc_up() { pgrep -x "$1" >/dev/null 2>&1; }
display_up() { [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; }
vnc_up() { pgrep -f "x11vnc.*-rfbport ${1}( |$)" >/dev/null 2>&1; }
novnc_up() { pgrep -f "websockify.*${NOVNC_PORT}" >/dev/null 2>&1; }

# --- display: the virtual monitor (required for any GL rendering) -------------
start_display() {
  if ! display_up; then
    Xvfb ":${DISPLAY_NUM}" -screen 0 "${GEOMETRY}x${DEPTH}" \
      +extension GLX +extension RANDR +render -noreset >/tmp/xvfb.log 2>&1 &
    # Wait for the display socket before anything connects to it.
    for _ in $(seq 1 20); do
      display_up && break
      sleep 0.25
    done
    log "Xvfb on :${DISPLAY_NUM} (${GEOMETRY}x${DEPTH})"
  fi
  # Window manager so RViz/Gazebo windows are decorated, movable and resizable.
  if ! proc_up fluxbox; then
    fluxbox >/tmp/fluxbox.log 2>&1 &
    log "fluxbox window manager"
  fi
}

stop_display() {
  stop_novnc
  stop_vnc
  proc_up fluxbox && pkill -x fluxbox 2>/dev/null || true
  display_up && pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
  log "display stopped"
}

# --- vnc: native, password-protected VNC server (5901) -----------------------
start_vnc() {
  start_display
  if ! vnc_up "${VNC_PORT}"; then
    x11vnc -storepasswd "${VNC_PASSWORD}" "${VNC_PASSWD_FILE}" >/dev/null 2>&1
    x11vnc -display ":${DISPLAY_NUM}" -forever -shared \
      -rfbauth "${VNC_PASSWD_FILE}" -rfbport "${VNC_PORT}" -bg -quiet >/tmp/x11vnc.log 2>&1
    log "VNC server on :${VNC_PORT} (password: ${VNC_PASSWORD})"
  fi
}

stop_vnc() {
  pkill -f "x11vnc.*-rfbport ${VNC_PORT}( |$)" 2>/dev/null || true
  # Wait for exit so a status check right after (the launcher rebuilds immediately
  # after Apply) reflects the real state instead of a still-dying process.
  for _ in $(seq 1 15); do vnc_up "${VNC_PORT}" || break; sleep 0.1; done
}

# --- novnc: browser viewer (own passwordless backend on 5902 + websockify) ----
start_novnc() {
  start_display
  if ! command -v websockify >/dev/null 2>&1 || [ ! -d /usr/share/novnc ]; then
    log "noVNC not installed (websockify / /usr/share/novnc missing)"
    return 0
  fi
  # Dedicated localhost-only, passwordless VNC backend so the browser connects
  # without a prompt while the native VNC endpoint stays password-protected.
  if ! vnc_up "${NOVNC_VNC_PORT}"; then
    x11vnc -display ":${DISPLAY_NUM}" -forever -shared \
      -nopw -localhost -rfbport "${NOVNC_VNC_PORT}" -bg -quiet >/tmp/x11vnc-novnc.log 2>&1
  fi
  if ! novnc_up; then
    websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${NOVNC_VNC_PORT}" \
      >/tmp/novnc.log 2>&1 &
    log "noVNC on http://localhost:${NOVNC_PORT}/vnc.html (no password)"
  fi
}

stop_novnc() {
  pkill -f "websockify.*${NOVNC_PORT}" 2>/dev/null || true
  pkill -f "x11vnc.*-rfbport ${NOVNC_VNC_PORT}( |$)" 2>/dev/null || true
  # Wait for exit so an immediate status check reflects the real state.
  for _ in $(seq 1 15); do novnc_up || break; sleep 0.1; done
}

usage() { echo "usage: $0 {display|vnc|novnc} {start|stop|status} | {start|stop}" >&2; exit 2; }

component="${1:-start}"
action="${2:-start}"
case "$component" in
  display)
    case "$action" in
      start)  start_display ;;
      stop)   stop_display ;;
      status) display_up ;;
      *) usage ;;
    esac ;;
  vnc)
    case "$action" in
      start)  start_vnc ;;
      stop)   stop_vnc ;;
      status) vnc_up "${VNC_PORT}" ;;
      *) usage ;;
    esac ;;
  novnc)
    case "$action" in
      start)  start_novnc ;;
      stop)   stop_novnc ;;
      status) novnc_up ;;
      *) usage ;;
    esac ;;
  start) start_display; start_vnc; start_novnc ;;
  stop)  stop_novnc; stop_vnc; stop_display ;;
  *) usage ;;
esac
