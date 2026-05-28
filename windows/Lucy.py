# This script provides a native Windows TUI for managing the Lucy workspace.
# It replicates the logic of the .sh scripts by calling git and docker directly.
# This script is designed to be compiled into a standalone .exe file.
#
# PREREQUISITES for running from source:
# 1. Python 3
# 2. Git for Windows (must be in your PATH)
# 3. Docker Desktop for Windows (must be running)
#

import os
import subprocess
import sys
import json

# --- Platform Check ---
if sys.platform != "win32":
    print("Error: This script is designed for Windows only.", file=sys.stderr)
    sys.exit(1)

# --- Configuration ---
# When running as a PyInstaller executable, the script is extracted to a temp folder.
# We need to determine the project root relative to the executable's location.
if getattr(sys, 'frozen', False):
    # Running as a compiled executable
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    # Running as a .py script
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
REPOS_FILE = os.path.join(PROJECT_ROOT, "config", "repos.json")
DOCKERFILE = os.path.join(PROJECT_ROOT, "Dockerfile.humble")
IMAGE_NAME = "lucy_ros2:humble"
WORKSPACE_DIR_HOST = PROJECT_ROOT
WORKSPACE_DIR_CONTAINER = "/workspace"

# --- Helper Functions ---

def run_command(command, check=True, interactive=False):
    """Runs a command, streaming its output if not interactive."""
    print(f"--- Running: {' '.join(command)} ---")
    try:
        if interactive:
            # For interactive commands, run directly and attach to the terminal.
            return subprocess.run(command, check=check).returncode
        else:
            # For non-interactive commands, capture and stream output.
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(process.stdout.readline, ''):
                print(line.strip())
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

def get_dev_mode():
    if not os.path.exists(ENV_FILE):
        return False
    with open(ENV_FILE, "r") as f:
        for line in f:
            if line.strip().startswith("DEV="):
                return line.strip().split("=")[1].lower() == "true"
    return False

def set_dev_mode(is_enabled):
    lines = []
    dev_found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    with open(ENV_FILE, "w") as f:
        for line in lines:
            if line.strip().startswith("DEV="):
                f.write(f"DEV={str(is_enabled).lower()}\n")
                dev_found = True
            else:
                f.write(line)
        if not dev_found:
            f.write(f"DEV={str(is_enabled).lower()}\n")

def _format_volume_mapping(host_path, container_path):
    """
    Return a Docker -v mapping string without extra quotes.
    Normalize host path to an absolute path and use forward slashes to avoid
    passing literal quote characters into the docker CLI.
    """
    host_abs = os.path.abspath(host_path)
    # Use forward slashes to reduce issues with escaping backslashes;
    # Docker Desktop accepts Windows-style paths with forward slashes.
    host_normalized = host_abs.replace('\\', '/')
    return f"{host_normalized}:{container_path}"

# --- Core Logic Functions ---

def clone_or_update_repos():
    """Clones or updates repositories based on repos.json."""
    is_dev = get_dev_mode()
    print(f"Developer mode is {'ON' if is_dev else 'OFF'}.")

    with open(REPOS_FILE, 'r') as f:
        repos = json.load(f)['repos']

    src_dir = os.path.join(PROJECT_ROOT, 'src')
    os.makedirs(src_dir, exist_ok=True)

    for repo in repos:
        repo_name = repo['name']
        repo_path = os.path.join(src_dir, repo_name)
        url_key = 'url_ssh' if is_dev else 'url_https'
        repo_url = repo[url_key]
        branch = repo['branch']

        if os.path.exists(os.path.join(repo_path, '.git')):
            print(f"Updating repo: {repo_name}")
            run_command(['git', '-C', repo_path, 'fetch'])
            run_command(['git', '-C', repo_path, 'checkout', branch])
            run_command(['git', '-C', repo_path, 'pull'])
        else:
            print(f"Cloning repo: {repo_name}")
            run_command(['git', 'clone', '-b', branch, repo_url, repo_path])

def build_docker_image():
    """Builds the main Docker image."""
    print("Building Docker image...")
    run_command(['docker', 'build', '-t', IMAGE_NAME, '-f', DOCKERFILE, '.'], check=True)

def build_workspace():
    """Runs the colcon build process inside the container."""
    print("Building workspace inside the container...")
    inner_cmd = (
        'source /opt/ros/humble/setup.bash && '
        'cd /workspace && '
        'rosdep install --from-paths src --ignore-src -r -y --skip-keys="audio_common" && '
        'colcon build --symlink-install && '
        'if [ -f src/lucy_control_panel/package.json ]; then '
        '(cd src/lucy_control_panel && yarn install); '
        'fi'
    )
    volume_mapping = _format_volume_mapping(WORKSPACE_DIR_HOST, WORKSPACE_DIR_CONTAINER)
    # Do NOT include an extra 'bash' argument; the image sets ENTRYPOINT to /bin/bash.
    # Provide '-c' so the entrypoint receives the command string correctly.
    docker_cmd = [
        'docker', 'run', '--rm',
        '-v', volume_mapping,
        IMAGE_NAME,
        '-c', inner_cmd
    ]
    run_command(docker_cmd)


def _docker_gui_args():
    """Return Docker args for optional GUI/X11 forwarding."""
    gui_display = os.environ.get('DOCKER_GUI_DISPLAY', os.environ.get('DISPLAY', '')).strip()
    if sys.platform == 'win32' and not gui_display:
        # Docker Desktop can reach the Windows X server at host.docker.internal.
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

    docker_cmd = ['docker', 'run', '--rm'] + gui_args + [IMAGE_NAME, '-c', f'python3 -c "{python_check}"']
    run_command(docker_cmd, check=False)


def launch_workspace():
    """Launches the main tmux session in the container."""
    print("Launching workspace...")

    container_script = (
        "source /opt/ros/humble/setup.bash && "
        "cd /workspace && source install/setup.bash && "
        "tmux start-server && "
        "if ! tmux has-session -t lucy_ws 2>/dev/null; then "
        "tmux new-session -d -s lucy_ws -n 'Lucy Workspace' 'python3 /workspace/launcher.py'; "
        "fi && "
        "tmux attach-session -t lucy_ws"
    )

    volume_mapping = _format_volume_mapping(WORKSPACE_DIR_HOST, WORKSPACE_DIR_CONTAINER)
    gui_args = _docker_gui_args()
    display_value = os.environ.get('DOCKER_GUI_DISPLAY', os.environ.get('DISPLAY', ''))
    if sys.platform == 'win32' and not display_value:
        display_value = 'host.docker.internal:0'

    if gui_args:
        print(f"Enabling GUI forwarding with DISPLAY={display_value}")
        _docker_gui_diagnostics(display_value, gui_args)
    else:
        print("No DISPLAY configured; running without GUI.")

    # Remove the extra 'bash' token; pass '-c' so the ENTRYPOINT (/bin/bash) runs the script.
    docker_cmd = [
        'docker', 'run', '-it', '--rm',
        '--name', 'lucy_dev_win',
        '-p', '9090:9090',
        '-p', '5000:5000',
        '-v', volume_mapping,
    ] + gui_args + [
        IMAGE_NAME,
        '-c', container_script
    ]
    
    run_command(docker_cmd, interactive=True)


# --- Main TUI ---

def main():
    while True:
        is_dev_mode = get_dev_mode()
        dev_status = "ON" if is_dev_mode else "OFF"
        
        print("\n--- Lucy Workspace Manager (Native Windows) ---")
        print(f"1. Toggle Developer Mode (Currently: {dev_status})")
        print("2. Install (Full)")
        print("3. Rebuild (Workspace only)")
        print("4. Launch")
        print("5. Exit")
        
        try:
            choice = input("\nEnter your choice (1-5): ").strip()
        except KeyboardInterrupt:
            break

        if choice == '1':
            set_dev_mode(not is_dev_mode)
            print(f"Developer mode set to: {'ON' if not is_dev_mode else 'OFF'}")
        
        elif choice == '2':
            clone_or_update_repos()
            build_docker_image()
            build_workspace()
            print("--- Full install complete! ---")
        
        elif choice == '3':
            build_workspace()
            print("--- Workspace rebuild complete! ---")
        
        elif choice == '4':
            launch_workspace()
            
        elif choice == '5':
            break
        
        else:
            print("Invalid choice, please try again.")
            
        if choice != '4' and choice != '5':
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    # This needs to be at the top level for PyInstaller to see it.
    os.chdir(PROJECT_ROOT)
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)