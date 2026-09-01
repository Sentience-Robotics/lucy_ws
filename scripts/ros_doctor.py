#!/usr/bin/env python3
"""Run `ros2 doctor --report` without letting DDS discovery hang the caller.

`ros2 doctor` waits on the middleware, and on hosts where multicast cannot be
routed the wait never ends: on a macOS CI runner Cyclone picked a virtual
interface, failed every `ddsi_udp_conn_write` to 239.255.0.1, and the job sat
there until the 2h limit. Scope discovery to localhost so the report is about
this machine, and cap the runtime so a stuck middleware fails fast.
"""

from __future__ import annotations

import os
import subprocess
import sys

TIMEOUT_S = float(os.environ.get("LUCY_DOCTOR_TIMEOUT_SEC", "180"))

# Setting the deprecated ROS_LOCALHOST_ONLY as well would take precedence and
# make rcl ignore this one, so leave it alone.
LOCALHOST_ENV = {"ROS_AUTOMATIC_DISCOVERY_RANGE": "LOCALHOST"}


def main() -> int:
    env = {**os.environ, **LOCALHOST_ENV}
    command = ["ros2", "doctor", "--report", *sys.argv[1:]]
    try:
        return subprocess.run(command, env=env, timeout=TIMEOUT_S, check=False).returncode
    except subprocess.TimeoutExpired:
        print(
            f"ros2 doctor did not finish within {TIMEOUT_S:.0f}s even with discovery "
            "scoped to localhost — the middleware is stuck, not slow.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"could not run {command[0]}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
