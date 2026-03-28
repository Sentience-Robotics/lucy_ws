# Lucy: simulation, visualization, and control panel pipeline

Technical developer documentation for the path from the web control panel through `ros2_control`, `thais_urdf`, RViz2, and Gazebo. Assumes ROS 2 (Humble) familiarity.

### Severity levels (gaps vs standards)

| Level | Meaning |
|-------|--------|
| **Critical** | Safety, determinism, or integration breaks; fix before production or reliable sim. |
| **High** | Maintainability, correctness risk, or frequent operational failure; plan soon. |
| **Medium** | Best-practice drift; improves robustness, debuggability, or portability. |
| **Low** | Polish, naming, or optional enhancements. |

Sections **1–6** each include a **Next improvements** subsection: gaps vs typical **ROS 2 Humble** and **robotics/industry** integration patterns, with **severity** in the first column of each table.

## Table of contents

1. [Control panel → actuator commands](#1-control-panel--actuator-commands)
2. [`lucy_ros2_control`](#2-lucy_ros2_control)
3. [`thais_urdf` package](#3-thais_urdf-package)
4. [RViz2](#4-rviz2)
5. [Gazebo](#5-gazebo)
6. [Workspace notes](#6-workspace-notes)

---

## 1. Control panel → actuator commands

### Where messages are built

- **Type**: `trajectory_msgs/msg/JointTrajectory` (full message: `header`, `joint_names`, `points[]`).
- **Code**: `lucy_control_panel/src/Services/ros/handlers/JointState.handler.ts` — `publishJointStates()` builds a `ROSLIB.Message` with:
  - `header.stamp` from `/clock` when available (for `use_sim_time`), else wall time
  - `joint_names` and one point with `positions` (radians) and `time_from_start` **0.2 s** (so the trajectory controller accepts the goal)

### Where topics and joint lists are defined

- **Static UI config**: `lucy_control_panel/src/Constants/rosConfig.ts` — `CONTROLLER_JOINTS_CONFIG` lists per controller:
  - `topic` (e.g. `/left_arm_controller/joint_trajectory`, `/right_arm_controller/joint_trajectory`)
  - `joints[]` (order must match the `JointTrajectoryController` config in `lucy_controllers.yaml`)
  - `defaultCategory` (UI grouping)

Keep this file aligned with `lucy_ros2_control/config/lucy_controllers.yaml`.

- **Dynamic override (optional)**: `CONTROLLER_JOINTS_TOPIC` = `/lucy_control_panel/controller_joints` (`std_msgs/String` JSON: `{ "controllers": ControllerJointConfig[] }`). `RobotControlPanel.tsx` applies updates when valid JSON is received. There is **no publisher** for this topic in the workspace by default; the panel relies on static config unless you add a ROS node.

- **Message type string**: `ROS_CONFIG.jointStateTopic.messageType` → `trajectory_msgs/msg/JointTrajectory`.

### Runtime behavior

- With **sending** enabled, a **300 ms** interval calls `publishJointStates` (`REFRESH_RATE` in `RobotControlPanel.tsx`).
- **`robotConfig.ts`** (URDF/mesh paths for the web 3D viewer) is **not** part of the ROS command pipeline.

### Next improvements: control panel ↔ ROS

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **Command API**: Panel publishes **open-loop** `JointTrajectory` points on a **topic** at a fixed rate (streaming setpoints). | **High** | For arms, common pattern is **`FollowJointTrajectory` action** (`control_msgs/action/FollowJointTrajectory`) or the controller’s **action server** exposed by `joint_trajectory_controller`, with goals that include tolerances, cancellation, and result feedback. Streaming topic goals work but bypass action semantics, make error handling and **rejection** handling weaker, and are harder to integrate with MoveIt 2 / Nav2-style stacks. |
| **Triplication of truth**: `rosConfig.ts`, `lucy_controllers.yaml`, and xacro must stay aligned **manually**. | **High** | Single source: generate client config from the same YAML/URDF (build step), or **publish** controller metadata from ROS (`list_controllers` + parameters, custom msg, or **`robot_state_publisher` + parameter** patterns). Reduces drift that causes silent wrong joint order. |
| **Dynamic config on `std_msgs/String` JSON** | **Medium** | Prefer a **typed interface**: custom `.msg`, **`controller_manager` introspection**, or a small **service** returning structured data. Easier validation, versioning, and `ros2 interface` tooling. |
| **`time_from_start` / rate**: Magic **0.2 s** and **300 ms** loop are tuning hacks. | **Medium** | Trajectories should respect controller **`constraints`** / **`allow_integration_in_goal_trajectories`** and desired time scaling; for teleop, **position commands** or **velocity** interfaces are sometimes clearer than repeated full trajectories (depends on controller mode). Document the chosen contract. |
| **Clock**: Stamp from `/clock` when present; else wall time. | **Medium** | If `use_sim_time` is true but `/clock` is missing, stamping with wall time **breaks** time coherence for TF and control. Fail closed (don’t send) or block UI until `/clock` is available in sim. |
| **Limits**: Default **0…π** in UI vs URDF `limit` per joint. | **Medium** | Derive limits from **`/robot_description`** (parse once) or a **`sensor_msgs/JointState`-like** metadata topic so commands respect hardware/software limits. |

---

## 2. `lucy_ros2_control`

### Layout

| Artifact | Role |
|----------|------|
| `config/lucy_controllers.yaml` | `controller_manager` plugins: `joint_state_broadcaster`, `left_arm_controller`, `right_arm_controller` (`joint_trajectory_controller/JointTrajectoryController`). Defines `joints`, `command_interfaces` / `state_interfaces` (position). |
| `hardware/lucy_system.cpp` | **Real hardware**: `LucySystemHardware` (see `lucy_ros2_control.xml`). |
| `launch/control.launch.py` | Real stack: `robot_state_publisher` + delayed `ros2_control_node` + spawners. No RViz, no rosbridge. |

### URDF integration

- `thais_urdf/inmoov/ros2_control/inmoov_ros2_control.xacro` declares two `<ros2_control>` systems:
  - **Real**: plugin `lucy_ros2_control/LucySystemHardware`, params `joints/left_arm`, `joints/right_arm`.
  - **Gazebo**: plugin `gz_ros2_control/GazeboSimSystem` when `use_gazebo_sim:=true`.

### Changing controllers or joints

1. Edit `config/lucy_controllers.yaml`.
2. Match joint names in `inmoov_ros2_control.xacro`.
3. Match `CONTROLLER_JOINTS_CONFIG` in `rosConfig.ts`.
4. Rebuild if the hardware plugin changes.

### Config caveat

- `joint_state_broadcaster` **`extra_joints`** lists passive joints but **also** includes names present on the arm controllers (e.g. `left_shoulder_z_link_joint`, `right_shoulder_z_link_joint`). A joint should not be both fully controlled and listed as extra—audit for duplicate or inconsistent `/joint_states` entries.

### Next improvements: `lucy_ros2_control`

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **`extra_joints` overlap** with joints commanded by JTC | **High** | `joint_state_broadcaster` should publish **one** consistent value per joint. `extra_joints` is for joints **not** claimed by hardware interfaces; controlled joints must not appear twice. Fix YAML to match [ros2_control docs](https://control.ros.org/) for broadcaster behavior. |
| **Two `<ros2_control>` system tags** (left/right) | **Medium** | Often consolidated into **one** system with one hardware plugin (or one sim plugin) for simpler resource management. Multiple systems are valid but increase **complexity** and spawn-order sensitivity; prefer one block if hardware allows. |
| **Hardware plugin namespace** (`ros2_control_demo_example_2` in source) | **Low** | Rename types/namespaces to **`lucy_ros2_control`** for clarity, logs, and vendor identification—matches REP-144 style package identity. |
| **Controller param file only** | **Low** | Humble supports YAML + overrides; consider **namespaced** params per robot variant and **`--param-file`** patterns for CI reproducibility. |
| **Testing** | **Medium** | Add **`ros2_control` hardware component tests** (mock interfaces) and **`launch_testing`** for bringup; industry workflows gate releases on these. |

---

## 3. `thais_urdf` package

**Install note**: `CMakeLists.txt` installs **`launch/`**, **`config/`**, and **`inmoov/`** into `share/thais_urdf`. Launch defaults use **`get_package_share_directory("thais_urdf")`** (binary installs and CI need only a sourced overlay).

| Path | Purpose |
|------|---------|
| `inmoov/urdf/inmoov.urdf.xacro` | Top-level xacro: `base_path`, `use_gazebo_sim`, `controller_config`; includes `robot_description`, `inmoov_ros2_control`, and conditionally `inmoov_gazebo.xacro`. |
| `inmoov/3dmodel/robot_description.urdf.xacro` | Main InMoov URDF (links, joints, meshes). |
| `inmoov/ros2_control/inmoov_ros2_control.xacro` | ros2_control blocks and joint interfaces. |
| `inmoov/ros2_control/inmoov_gazebo.xacro` | Static `base_node` / `stand_link`; `gz_ros2_control::GazeboSimROS2ControlPlugin` with `controller_config`. |
| `launch/rviz.launch.py` | Real robot: xacro without sim, `robot_state_publisher`, `ros2_control_node` + spawners, rosbridge, RViz (`use_sim_time: false`). |
| `launch/gazebo.launch.py` | Gz Sim, clock bridge, `robot_state_publisher` (`use_sim_time: true`), delayed spawn, Gazebo env, controller spawners (no separate `ros2_control_node`—plugin hosts `controller_manager`), rosbridge, RViz. |
| `config/inmoov_rviz.rviz` | Saved RViz layout. |

### Next improvements: robot description package

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **URDF/meshes install + share paths** (historical gap) | **Done** | **`inmoov/`** installed to `share/thais_urdf`; default **`urdf_path` / `base_path`** use **`get_package_share_directory("thais_urdf")`** (`rviz` / `gazebo` / `lucy_ros2_control` `control.launch.py`). Override launch args if you need a forked xacro tree. |
| **Package name vs content** (`thais_urdf` vs InMoov model) | **Low** | Document clearly in `package.xml` / README; consider renaming for discoverability (optional, large churn). |
| **License / provenance** | **Medium** | InMoov-derived assets: ensure **LICENSE** files ship with installed share and are referenced in package metadata (common in industry compliance). |

---

## 4. RViz2

### Launch

- **Config**: `--display-config` → `share/thais_urdf/config/inmoov_rviz.rviz`.
- **Parameter**: `use_sim_time` — `false` in `rviz.launch.py`, `true` in `gazebo.launch.py`.

### Saved config (summary)

- **RobotModel**: description from `/robot_description`.
- **Fixed Frame**: `base_node`.
- **TF**: enabled.

### Data flow

- `joint_state_broadcaster` publishes **`/joint_states`**.
- `robot_state_publisher` uses **`/joint_states`** + URDF to publish **TF**.
- RViz uses **TF** + **`/robot_description`** for the robot model (not `/joint_states` directly).

### Next improvements: RViz

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **Fixed Frame `base_node`** | **Low** | Often **`odom`** or **`map`** for mobile systems; for fixed manipulators, **`world`** or base link is fine if TF tree is consistent. Document the chosen **root** and ensure no **disconnected trees** (use `tf2_tools view_frames`). |
| **Debugging joint values** | **Medium** | Add **`JointState`** display or **`rqt_joint_trajectory_controller`** for operators; production cells often standardize on a small set of RViz plugins for support. |
| **`use_sim_time` consistency** | **High** | All nodes in a sim session must agree; RViz already sets the param—ensure **every** node in the launch graph (including bridges) follows [sim time guidelines](https://docs.ros.org/en/humble/Tutorials/Intermediate/Simulators/Simulation-Time.html). |
| **Saved `.rviz` in repo** | **Low** | Pin **RViz version** in docs; large diffs on re-save are normal—consider minimal configs or **YAML anchors** discipline. |

---

## 5. Gazebo

### Implemented

- `gazebo.launch.py`: `ros_gz_sim` (e.g. `empty.sdf`), `/clock` bridge, Gazebo resource/plugin paths, xacro with `use_gazebo_sim:=true` and `controller_config`, `gz_ros2_control` plugin, spawners, RViz, rosbridge.
- `inmoov_gazebo.xacro`: static base links to stabilize the model.

### Next improvements: Gazebo + `gz_ros2_control`

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **Spawn vs spawner race** | **Critical** | `controller_manager` services must be **available** before `spawner` runs. Use **delayed spawners**, `OnProcessExit`, **`RegisterEventHandler`**, or **retry loops** (as in upstream `ros2_control` + Gazebo examples). Unreliable launches are a top cause of “works on my machine.” |
| **Static links for base** | **Medium** | Common for fixed-base arms; document that **inertial realism** and **contact** are traded for stability. For wheeled or legged next steps, remove static and tune **physics plugins**. |
| **`gz_ros2_control` + plugin paths** | **High** | Pin **Gazebo (Fortress/Harmonic)** and **`ros_gz`** to the [supported combination for Humble](https://gazebosim.org/docs/latest/ros_installation/); avoid hardcoded `/opt/ros/humble/...` fallbacks without checks—use `ament_index` or `get_package_prefix`. |
| **Empty world only** | **Low** | Add a **versioned SDF world** (ground plane, lighting, physics presets) for repeatable regression. |
| **Sensors / bridges** | **Medium** | Add **`ros_gz_bridge`** entries per sensor when needed; industry sims usually replicate **camera depth + clock** at minimum for perception stacks. |
| **Two ros2_control systems in sim** | **Medium** | Same as §2: prefer **one** sim hardware block if possible to match **official gz_ros2_control** examples. |

### “Working” checklist

1. Launch completes without controller spawn errors.
2. Controllers active: `joint_state_broadcaster`, `left_arm_controller`, `right_arm_controller`.
3. `/joint_states` and TF update; RViz tracks the model; panel trajectories move the arms in sim.
4. Sim time: RViz and `robot_state_publisher` use sim time; panel uses `/clock` when present.

---

## 6. Workspace notes

- Root `lucy_ws/README.md` may refer to **`inmoov_urdf`** while the package name is **`thais_urdf`**—same functional area, different name.
- Keep **`rosConfig.ts`** and **`lucy_controllers.yaml`** in sync if you duplicate the control panel repo.

### Next improvements: workspace & process

| Gap | Severity | Standard / good practice (Humble & industry) |
|-----|----------|-----------------------------------------------|
| **README package name mismatch** (`inmoov_urdf` vs `thais_urdf`) | **Low** | Align documentation names with **`package.xml`** to reduce onboarding friction. |
| **No automated sync** between panel and ROS YAML | **High** | Same as §1: CI check that joint lists match, or codegen from one artifact. |
| **Docker / `launch_lucy.sh` vs bare metal** | **Medium** | Document **ROS_DOMAIN_ID**, **network** for rosbridge, and **X11**/`WAYLAND` for RViz/Gazebo; industry teams often provide a **compose** or **devcontainer** matrix. |
| **REP compliance** | **Low** | Where applicable, align frame naming and topic naming with [REP-105](https://www.ros.org/reps/rep-0105.html) / team conventions. |

### Common commands (inside sourced workspace)

```bash
# Real + RViz + rosbridge
ros2 launch thais_urdf rviz.launch.py

# Real hardware stack only
ros2 launch lucy_ros2_control control.launch.py

# Gazebo + RViz + rosbridge
ros2 launch thais_urdf gazebo.launch.py
```

Optional launch args: `urdf_path:=<path>` `base_path:=<path>`.
