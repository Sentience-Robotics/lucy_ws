# POC hardware with 3d view

## Firmware
0.1. Build firmware
cd src/lucy_embedded_firmware/firmwares/rp2040
cargo build --release -p lucy_embedded_firmware_rp2040 --target thumbv6m-none-eabi

0.2. Convert firmware to UF2
elf2uf2-rs target/thumbv6m-none-eabi/release/lucy_embedded_firmware_rp2040 lucy_embedded_firmware_rp2040

0.3. Flash rp2040
sudo picotool load -fx lucy_embedded_firmware_rp2040.uf2

1. Run core
pixi shell
LUCY_BUS_SERVO_ID=6 LUCY_ROBOT_PACKAGE=so_arm101_urdf ros2 launch lucy_bringup lucy.launch.py real:=true robot_package:=so_arm101_urdf

2. Run control panel
pixi run panel-dev

3. Run firmware
cd src/lucy_embedded_firmware/firmwares/sim
cargo run -- so_arm

## repos.json.local

{
  "repos": [
    {
      "name": "inmoov_urdf",
      "branch": "aes/fix-mimic-joints",
      "url_https": "https://github.com/Sentience-Robotics/inmoov_urdf.git",
      "url_ssh": "git@github.com:Sentience-Robotics/inmoov_urdf.git"
    },
    {
      "name": "lucy_ros_packages",
      "branch": "aes/fix-macos",
      "url_https": "https://github.com/Sentience-Robotics/lucy_ros_packages.git",
      "url_ssh": "git@github.com:Sentience-Robotics/lucy_ros_packages.git"
    },
    {
      "name": "lucy_control_panel",
      "branch": "sbr/fix-sliders-limit",
      "url_https": "https://github.com/Sentience-Robotics/lucy_control_panel.git",
      "url_ssh": "git@github.com:Sentience-Robotics/lucy_control_panel.git"
    },
    {
      "name": "so_arm101_urdf",
      "branch": "aes/fix-macos",
      "url_https": "https://github.com/Sentience-Robotics/so_arm101_urdf.git",
      "url_ssh": "git@github.com:Sentience-Robotics/so_arm101_urdf.git"
    },
    {
      "name": "lucy_embedded_firmware",
      "branch": "aes/fix-macos",
      "url_https": "https://github.com/Sentience-Robotics/lucy_embedded_firmware.git",
      "url_ssh": "git@github.com:Sentience-Robotics/lucy_embedded_firmware.git"
    }
  ]
}
