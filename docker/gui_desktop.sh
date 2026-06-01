#!/usr/bin/env bash
# Self-contained virtual desktop for GUI apps that need OpenGL (RViz, Gazebo).
#
# Runs entirely inside the container: an Xvfb display rendered by Mesa llvmpipe
# (software GL), a small window manager, and a VNC + noVNC server so the desktop
# can be viewed from the host. This is used on hosts whose own X server cannot
# give the container an OpenGL/GLX context — notably macOS XQuartz, where RViz and
# Gazebo otherwise fail with "Unable to create a suitable GLXContext".
#
# launch_lucy.sh starts this (start) on macOS before launching the ROS stack, with
# DISPLAY=:99 exported so RViz/Gazebo render here. View it from the host with:
#   • macOS Screen Sharing:  open vnc://localhost:5901
#   • Browser (noVNC):       http://localhost:6080/vnc.html
set -u

DISPLAY_NUM="${LUCY_GUI_DISPLAY_NUM:-99}"
GEOMETRY="${LUCY_GUI_GEOMETRY:-1600x900}"
DEPTH=24
VNC_PORT="${LUCY_GUI_VNC_PORT:-5901}"
NOVNC_PORT="${LUCY_GUI_NOVNC_PORT:-6080}"
NOVNC_VNC_PORT="${LUCY_GUI_NOVNC_VNC_PORT:-5902}"
NOVNC_PASSWORDLESS="${LUCY_GUI_NOVNC_PASSWORDLESS:-0}"
# Native VNC clients (macOS Screen Sharing, RealVNC Viewer) refuse a no-auth
# server, so we always set a VNC password. The VNC auth scheme only uses the
# first 8 characters. Override with LUCY_GUI_VNC_PASSWORD.
VNC_PASSWORD="${LUCY_GUI_VNC_PASSWORD:-lucy}"
VNC_PASSWD_FILE=/tmp/.lucy_vncpasswd
export DISPLAY=":${DISPLAY_NUM}"

log() { echo "[gui_desktop] $*"; }
# Match by exact process name (comm), not full command line, so these checks can't
# accidentally match the surrounding shell whose argv may mention these binaries.
proc_up() { pgrep -x "$1" >/dev/null 2>&1; }
display_up() { [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; }
vnc_up() { pgrep -f "x11vnc.*-rfbport ${1}( |$)" >/dev/null 2>&1; }

start() {
  # Virtual X display with GLX so Mesa llvmpipe can create GL contexts.
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

  # VNC server bound to the virtual display, password-protected so native VNC
  # clients (macOS Screen Sharing, RealVNC Viewer) can authenticate.
  if ! vnc_up "${VNC_PORT}"; then
    x11vnc -storepasswd "${VNC_PASSWORD}" "${VNC_PASSWD_FILE}" >/dev/null 2>&1
    x11vnc -display ":${DISPLAY_NUM}" -forever -shared \
      -rfbauth "${VNC_PASSWD_FILE}" -rfbport "${VNC_PORT}" -bg -quiet >/tmp/x11vnc.log 2>&1
    log "VNC server on :${VNC_PORT} (password: ${VNC_PASSWORD})"
  fi

  # Separate localhost-only VNC endpoint for noVNC so the browser can connect
  # without prompting for a password while native VNC clients stay protected.
  if [ "${NOVNC_PASSWORDLESS}" = "1" ] && ! vnc_up "${NOVNC_VNC_PORT}"; then
    x11vnc -display ":${DISPLAY_NUM}" -forever -shared \
      -nopw -localhost -rfbport "${NOVNC_VNC_PORT}" -bg -quiet >/tmp/x11vnc-novnc.log 2>&1
    log "Passwordless noVNC backend on localhost:${NOVNC_VNC_PORT}"
  fi

  # noVNC (browser client) when the package is available.
  if command -v websockify >/dev/null 2>&1 && [ -d /usr/share/novnc ]; then
    if ! pgrep -f "websockify.*${NOVNC_PORT}" >/dev/null 2>&1; then
      target_port="${VNC_PORT}"
      if [ "${NOVNC_PASSWORDLESS}" = "1" ]; then
        target_port="${NOVNC_VNC_PORT}"
      fi
      websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${target_port}" \
        >/tmp/novnc.log 2>&1 &
      if [ "${NOVNC_PASSWORDLESS}" = "1" ]; then
        log "noVNC on http://localhost:${NOVNC_PORT}/vnc.html (no password)"
      else
        log "noVNC on http://localhost:${NOVNC_PORT}/vnc.html"
      fi
    fi
  fi
}

stop() {
  pkill -f "websockify.*${NOVNC_PORT}" 2>/dev/null || true
  pkill -x x11vnc 2>/dev/null || true
  pkill -x fluxbox 2>/dev/null || true
  pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
}

case "${1:-start}" in
  start) start ;;
  stop)  stop ;;
  *) echo "usage: $0 {start|stop}" >&2; exit 2 ;;
esac
