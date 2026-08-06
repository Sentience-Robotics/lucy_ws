# Windows launcher for the Lucy workspace.
#
# Compiled to Lucy.exe via PyInstaller. Default behaviour: start the workspace
# (Docker + tmux + launcher). Install/update/repair is handled by Lucy-Setup.exe
# via the hidden --cli mode (see windows/install_runner.py).
#
# PREREQUISITES:
# 1. Docker Desktop for Windows (must be running)
# 2. Workspace must be installed (run Lucy-Setup.exe first)

import os
import subprocess
import sys

if sys.platform != "win32":
    print("Error: This script is designed for Windows only.", file=sys.stderr)
    sys.exit(1)

_WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
if _WINDOWS_DIR not in sys.path:
    sys.path.insert(0, _WINDOWS_DIR)

import install_ops  # noqa: E402

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(_WINDOWS_DIR)

IMAGE_NAME = install_ops.IMAGE_NAME
WORKSPACE_DIR_HOST = PROJECT_ROOT
WORKSPACE_DIR_CONTAINER = install_ops.WORKSPACE_CONTAINER

LCP_DEFAULT_PORT = 3000

_CLI_MODES = frozenset(('install', 'update', 'repair', 'build-only', 'check-prereqs'))


def run_command(command, check=True, interactive=False):
    """Runs a command, streaming its output if not interactive."""
    print(f"--- Running: {' '.join(command)} ---")
    try:
        if interactive:
            return subprocess.run(command, check=check).returncode
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ''):
            print(line.rstrip())
        process.wait()
        if check and process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
        return process.returncode
    except FileNotFoundError:
        print(f"Error: Command '{command[0]}' not found. Is it in your PATH?")
        return -1
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        return e.returncode


def _read_env_value(env_path, key):
    if not os.path.exists(env_path):
        return None
    value = None
    try:
        with open(env_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('#') or '=' not in stripped:
                    continue
                if stripped.startswith(f"{key}="):
                    value = stripped.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return value


def _read_lcp_env_value(key):
    return _read_env_value(os.path.join(PROJECT_ROOT, 'src', 'lucy_control_panel', '.env'), key)


def _read_root_env_value(key):
    return _read_env_value(os.path.join(PROJECT_ROOT, '.env'), key)


def _lcp_container_port():
    val = _read_lcp_env_value('VITE_PORT')
    if val and val.isdigit():
        return int(val)
    return LCP_DEFAULT_PORT


def _lcp_scheme():
    val = _read_lcp_env_value('VITE_HTTPS')
    if val and val.strip().lower() == 'true':
        return 'https'
    return 'http'


def _docker_gui_args():
    gui_display = os.environ.get('DOCKER_GUI_DISPLAY', os.environ.get('DISPLAY', '')).strip()
    if sys.platform == 'win32' and not gui_display:
        gui_display = 'host.docker.internal:0'

    if not gui_display:
        return []

    args = ['-e', f'DISPLAY={gui_display}', '-e', 'QT_X11_NO_MITSHM=1']

    if os.environ.get('DOCKER_GUI_USE_HOST_NETWORK'):
        if sys.platform == 'win32':
            print("WARNING: DOCKER_GUI_USE_HOST_NETWORK is not supported on Windows; using DISPLAY only.")
            return args
        return ['--network=host', '-e', 'DISPLAY=:0', '-e', 'QT_X11_NO_MITSHM=1']

    if sys.platform == 'win32':
        if 'host.docker.internal' in gui_display:
            args.extend(['--add-host', 'host.docker.internal:host-gateway'])
        return args

    return args + ['-v', '/tmp/.X11-unix:/tmp/.X11-unix:rw']


def _parse_display_host_port(display_value):
    if display_value.startswith(':'):
        return 'localhost', 6000 + int(display_value[1:].split('.')[0])
    host, _, display_str = display_value.rpartition(':')
    if not host:
        host = 'localhost'
    try:
        display_num = int(display_str)
    except ValueError:
        display_num = 0
    return host, 6000 + display_num


def _docker_gui_diagnostics(gui_display, gui_args):
    print("--- GUI diagnostics ---")
    print(f"DISPLAY value used inside the container: {gui_display}")
    host, port = _parse_display_host_port(gui_display)
    print(f"Checking TCP connectivity to X server at {host}:{port}...")

    python_check = (
        "import os, socket, sys\n"
        "display = os.environ.get('DISPLAY', '')\n"
        "print('container DISPLAY=' + display)\n"
        f"host = '{host}'\n"
        f"port = {port}\n"
        "try:\n"
        "    s = socket.create_connection((host, port), timeout=3)\n"
        "    print('OK: connected to', host, port)\n"
        "    s.close()\n"
        "except Exception as e:\n"
        "    print('FAIL: could not connect to', host, port, e)\n"
        "    sys.exit(1)\n"
    )

    docker_cmd = ['docker', 'run', '--rm'] + install_ops.docker_run_platform_args(PROJECT_ROOT) + gui_args + [IMAGE_NAME, '-c', f'python3 -c "{python_check}"']
    run_command(docker_cmd, check=False)


def launch_workspace():
    """Start Docker, attach to the Lucy Control Center launcher inside tmux."""
    if not os.path.isfile(os.path.join(PROJECT_ROOT, 'install', 'setup.bash')):
        print("Workspace not built. Run Lucy-Setup.exe to install or update first.", file=sys.stderr)
        sys.exit(1)

    print("Launching workspace...")

    container_script = (
        "source /opt/ros/humble/setup.bash && "
        "[ -f /opt/gz_ros2_control_ws/install/setup.bash ] && source /opt/gz_ros2_control_ws/install/setup.bash; "
        "cd /workspace && source install/setup.bash && "
        "tmux start-server && "
        "if ! tmux has-session -t lucy_ws 2>/dev/null; then "
        "tmux new-session -d -s lucy_ws -n 'Lucy Workspace' 'python3 /workspace/launcher.py'; "
        "fi && "
        "tmux attach-session -t lucy_ws"
    )

    volume_mapping = install_ops.format_volume_mapping(WORKSPACE_DIR_HOST, WORKSPACE_DIR_CONTAINER)
    gui_args = _docker_gui_args()
    display_value = os.environ.get('DOCKER_GUI_DISPLAY', os.environ.get('DISPLAY', ''))
    if sys.platform == 'win32' and not display_value:
        display_value = 'host.docker.internal:0'

    if gui_args:
        print(f"Enabling GUI forwarding with DISPLAY={display_value}")
        _docker_gui_diagnostics(display_value, gui_args)
    else:
        print("No DISPLAY configured; running without GUI.")

    lcp_container_port = _lcp_container_port()
    lcp_host_port = lcp_container_port
    lcp_scheme = _lcp_scheme()

    val = _read_root_env_value('PORT_ROSBRIDGE')
    rosbridge_host_port = int(val) if val and val.isdigit() else 9090

    docker_cmd = [
        'docker', 'run', '-it', '--rm',
        *install_ops.docker_run_platform_args(PROJECT_ROOT),
        '--name', 'lucy_dev_win',
        '-p', f'{rosbridge_host_port}:9090',
        '-p', f'{lcp_host_port}:{lcp_container_port}',
        '-v', volume_mapping,
        '-e', f'LUCY_LCP_PUBLISHED_HOST_PORT={lcp_host_port}',
        '-e', f'LUCY_LCP_CONTAINER_PORT={lcp_container_port}',
        '-e', f'LUCY_LCP_SCHEME={lcp_scheme}',
    ] + gui_args + [
        IMAGE_NAME,
        '-c', container_script
    ]

    run_command(docker_cmd, interactive=True)


def _is_cli_invocation():
    return len(sys.argv) > 1 and (sys.argv[1] == '--cli' or sys.argv[1] in _CLI_MODES)


def _run_cli():
    """Install/update/repair — used by Lucy-Setup.exe, not exposed in the default UX."""
    from install_runner import main as install_main
    argv = [a for a in sys.argv[1:] if a != '--cli']
    return install_main(argv)


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    try:
        if _is_cli_invocation():
            sys.exit(_run_cli())
        launch_workspace()
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
