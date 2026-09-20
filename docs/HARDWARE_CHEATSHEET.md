# POC hardware with 3d view

## Firmware
1. Linux Serial Port Access (one-time setup)
pixi run setup-udev

2. Build firmware
cd src/lucy_embedded_firmware/firmwares/rp2040
cargo build --release -p lucy_embedded_firmware_rp2040 --target thumbv6m-none-eabi

3. Convert firmware to UF2
elf2uf2-rs target/thumbv6m-none-eabi/release/lucy_embedded_firmware_rp2040 lucy_embedded_firmware_rp2040

4. Flash rp2040
sudo picotool load -fx lucy_embedded_firmware_rp2040.uf2

## Run

1. Run core
pixi shell
LUCY_ROBOT_PACKAGE=so_arm101_urdf ros2 launch lucy_bringup lucy.launch.py real:=true robot_package:=so_arm101_urdf

2. Run control panel
pixi run panel-dev

3. Run firmware
cd src/lucy_embedded_firmware/firmwares/sim
cargo run -- so_arm
