# This script provides a native Windows TUI for managing the Lucy workspace.
# It replicates the logic of the .sh scripts by calling git and docker directly.
# This script is designed to be compiled into a standalone .exe file.
#
# PREREQUISITES for running from source:
# 1. Python 3
# 2. Git for Windows (must be in the system's PATH)
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
    docker_cmd = [
        'docker', 'run', '--rm',
        '-v', f'"{WORKSPACE_DIR_HOST}:{WORKSPACE_DIR_CONTAINER}"',
        IMAGE_NAME,
        'bash', '-c', inner_cmd
    ]
    run_command(docker_cmd)

def launch_workspace():
    """Launches the main tmux session in the container."""
    print("Launching workspace...")
    
    container_script = (
        'source /opt/ros/humble/setup.bash && '
        'cd /workspace && source install/setup.bash && '
        'tmux start-server && '
        "if ! tmux has-session -t lucy_ws 2>/dev/null; then "
        "tmux new-session -d -s lucy_ws -n 'Lucy Workspace' 'launcher'; "
        'fi && '
        'tmux attach-session -t lucy_ws'
    )

    docker_cmd = [
        'docker', 'run', '-it', '--rm',
        '--name', 'lucy_dev_win',
        '-p', '9090:9090',
        '-p', '5000:5000',
        '-v', f'"{WORKSPACE_DIR_HOST}:{WORKSPACE_DIR_CONTAINER}"',
        IMAGE_NAME,
        'bash', '-c', container_script
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
