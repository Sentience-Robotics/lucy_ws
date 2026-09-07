#!/usr/bin/env bash
# DDS discovery scope for Pixi/RoboStack.
#
# The stack is co-located and the control panel reaches it over a websocket, not
# DDS, so discovery never needs to leave the host. Subnet discovery is the Jazzy
# default and merges anyone else's Lucy on the network into this graph: two
# robot_state_publishers, two controller_managers on the same joints.
#
# ROS_AUTOMATIC_DISCOVERY_RANGE is rcl's knob, so it binds every RMW. A
# CYCLONEDDS_URI would not: RMW_IMPLEMENTATION is pinned to Cyclone on macOS
# only, and Linux runs rmw_fastrtps_cpp where the URI is inert.
#
# ROS_LOCALHOST_ONLY is never set here: it is deprecated and takes precedence,
# which would make rcl ignore the range below.
#
# Override in .env:
#   LUCY_DDS_LOCALHOST=0             stock DDS (subnet discovery, all interfaces)
#   LUCY_DDS_PEERS=hostA,hostB       also reach ROS nodes on named machines
#   LUCY_DDS_RANGE=OFF               set the rcl range verbatim
#   LUCY_DDS_INTERFACE=192.168.1.5   pin CycloneDDS discovery to one address
#
# Source after Pixi activation, which is where RoboStack's ros_environment hook
# sets the range to SUBNET.

_lucy_want_localhost() {
  case "${LUCY_DDS_LOCALHOST:-1}" in
    0|false|no|off|disable) return 1 ;;
    *) return 0 ;;
  esac
}

_lucy_dds_range() {
  if [[ -n "${LUCY_DDS_RANGE:-}" ]]; then
    export ROS_AUTOMATIC_DISCOVERY_RANGE="${LUCY_DDS_RANGE}"
  elif _lucy_want_localhost; then
    export ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST"
  else
    export ROS_AUTOMATIC_DISCOVERY_RANGE="SUBNET"
  fi

  # Additive to localhost, not a replacement for it. rcl splits on ';'.
  local peers="${LUCY_DDS_PEERS:-}"
  if [[ -n "${peers}" ]]; then
    local joined="${peers//,/;}"
    export ROS_STATIC_PEERS="${joined//[[:space:]]/}"
  fi
}

# Interface pinning for CycloneDDS, on top of the range above.
_lucy_cyclone_uri() {
  [[ -n "${CYCLONEDDS_URI:-}" ]] && return 0

  local iface="${LUCY_DDS_INTERFACE:-}"
  local peers="${LUCY_DDS_PEERS:-}"
  local want_localhost=0
  _lucy_want_localhost && want_localhost=1

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

_lucy_dds_range
_lucy_cyclone_uri
