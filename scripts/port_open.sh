#!/usr/bin/env bash
# Exit 0 if a TCP port on the local host accepts a connection.
#
#   scripts/port_open.sh <port> [host]
#
# Used by config/launcher_config.json readiness probes, which need to know a
# service is actually serving rather than merely that a process exists.
#
# Three methods, because none is portable on its own:
#   bash /dev/tcp  fastest, but Debian-family bash is sometimes built without
#                  net redirections, where it fails identically to a closed port
#   nc -z          absent on minimal images
#   python socket  always present here (the launcher itself is Python)
#
# A failed method therefore never concludes "closed" — it falls through to the
# next one, and only an exhausted list reports the port shut.

port="${1:?usage: port_open.sh <port> [host]}"
host="${2:-127.0.0.1}"

if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
  exit 0
fi

if command -v nc >/dev/null 2>&1; then
  nc -z -G 2 -w 2 "${host}" "${port}" >/dev/null 2>&1 && exit 0
  nc -z -w 2 "${host}" "${port}" >/dev/null 2>&1 && exit 0
fi

probe='import socket, sys
try:
    socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2).close()
except OSError:
    sys.exit(1)'
for py in python3 python; do
  if command -v "${py}" >/dev/null 2>&1; then
    "${py}" -c "${probe}" "${host}" "${port}" >/dev/null 2>&1 && exit 0
    break
  fi
done

exit 1
