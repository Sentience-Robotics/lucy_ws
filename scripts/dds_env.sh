#!/usr/bin/env bash
# CycloneDDS discovery env for Pixi/RoboStack.
#
# macOS gates local-network traffic behind the Local Network privacy permission,
# granted per application. tmux daemonizes to PPID 1, so the tmux server carries
# its own identity rather than the launching terminal's, and Homebrew's tmux is
# never granted it. DDS multicast discovery is then dropped silently for every
# process the tmux server spawns — which is the entire Lucy stack. Nodes come up
# and advertise normally, but no participant ever discovers another, so rosbridge
# answers "Service /config/get does not exist" while config_pipeline_node is
# running and healthy. Nothing logs an error; discovery just never happens.
#
# Loopback is exempt from that permission, so default macOS to localhost-only
# unicast discovery. Nothing is lost: the whole stack is co-located, the control
# panel reaches it over the rosbridge websocket, and micro-ROS agents are serial.
#
# Override in .env:
#   LUCY_DDS_LOCALHOST=0             stock DDS (multicast, all interfaces)
#   LUCY_DDS_INTERFACE=192.168.1.5   pin discovery to one interface address
#   LUCY_DDS_PEERS=hostA,hostB       unicast peers, to reach other machines
# A CYCLONEDDS_URI you set yourself always wins and is left untouched.
#
# Source this from the innermost shell, before exec'ing ros2 (see
# scripts/pixi_lucy_launch.sh and launcher.py).

_lucy_dds_env() {
  # An explicit CycloneDDS config always wins.
  [[ -n "${CYCLONEDDS_URI:-}" ]] && return 0

  local iface="${LUCY_DDS_INTERFACE:-}"
  local peers="${LUCY_DDS_PEERS:-}"
  local want_localhost

  if [[ "$(uname -s)" == "Darwin" ]]; then
    want_localhost=1
  else
    want_localhost=0
  fi
  case "${LUCY_DDS_LOCALHOST:-${want_localhost}}" in
    0|false|no|off|disable) want_localhost=0 ;;
    *) want_localhost=1 ;;
  esac

  # Stock behaviour and nothing pinned: leave DDS entirely alone.
  if [[ "${want_localhost}" == "0" && -z "${iface}" && -z "${peers}" ]]; then
    return 0
  fi

  local multicast="true"
  if [[ "${want_localhost}" == "1" ]]; then
    multicast="false"
    [[ -n "${iface}" ]] || iface="127.0.0.1"
    [[ -n "${peers}" ]] || peers="localhost"
  fi

  local peer_xml="" p
  if [[ -n "${peers}" ]]; then
    local old_ifs="${IFS}"
    IFS=','
    for p in ${peers}; do
      p="${p//[[:space:]]/}"
      [[ -n "${p}" ]] && peer_xml="${peer_xml}<Peer address=\"${p}\"/>"
    done
    IFS="${old_ifs}"
  fi

  local iface_xml=""
  if [[ -n "${iface}" ]]; then
    iface_xml="<Interfaces><NetworkInterface address=\"${iface}\" multicast=\"${multicast}\"/></Interfaces>"
  fi

  export CYCLONEDDS_URI="<CycloneDDS xmlns=\"https://cdds.io/config\"><Domain id=\"any\">\
<General>${iface_xml}<AllowMulticast>${multicast}</AllowMulticast></General>\
<Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>60</MaxAutoParticipantIndex>\
<Peers>${peer_xml}</Peers></Discovery></Domain></CycloneDDS>"
}

_lucy_dds_env
