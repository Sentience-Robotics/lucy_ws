{
  inputs = {
    nix-ros-overlay.url = "github:lopsided98/nix-ros-overlay/master";
    nixpkgs.follows = "nix-ros-overlay/nixpkgs";
  };
  outputs = { self, nix-ros-overlay, nixpkgs }:
    nix-ros-overlay.inputs.flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [
            nix-ros-overlay.overlays.default
          ];
        };



        python-vcs = pkgs.python3Packages.buildPythonPackage rec {
            pname = "python-vcs2l";
            version = "1.1.7";
            pyproject = true;

            src = pkgs.python3Packages.fetchPypi {
                inherit version;
                pname = "vcs2l";
                hash = "sha256-HYbmhfngHdonG4nfGyvULKVVX1wNy+9cxyfUQ/JXOM0=";
            };

            build-system = [ pkgs.python3Packages.setuptools ];
            dependencies = [ pkgs.python313Packages.pyyaml ];
        };

        python-rosdistro = pkgs.python3Packages.buildPythonPackage rec {
            pname = "python-rosdistro";
            version = "1.0.1";
            pyproject = true;

            src = pkgs.python3Packages.fetchPypi {
                inherit version;
                pname = "rosdistro";
                hash = "sha256-J/iLS/CteekF6R2zdnS586JdEnrm5HuqvR4YBE1gwmw=";
            };

            build-system = [ pkgs.python3Packages.setuptools ];
            dependencies = [ pkgs.python313Packages.pyyaml
                             pkgs.python313Packages.catkin-pkg
                             pkgs.python313Packages.rospkg
            ];
        };


        python-rosdep = pkgs.python3Packages.buildPythonPackage rec {
            pname = "python-rosdep";
            version = "0.26.0";
            pyproject = true;

            src = pkgs.python3Packages.fetchPypi {
                inherit version;
                pname = "rosdep";
                hash = "sha256-xHQwAwWLwO7Udgf0Zh9dGnxQWKgwuMs6BAPu+gndba0=";
            };

            build-system = [ pkgs.python3Packages.setuptools ];
            dependencies = [ pkgs.python313Packages.pyyaml
                             pkgs.python313Packages.distutils
                             pkgs.python313Packages.catkin-pkg
                             pkgs.python313Packages.rospkg
                             python-rosdistro
            ];
        };

      in
    {
        devShells.default = pkgs.mkShell {
          name = "Lucy ROS dev shell";

          packages = [
            python-vcs
            python-rosdep

            pkgs.llvmPackages_20.clang-tools
            pkgs.python313Packages.black

            pkgs.colcon
            pkgs.cmake
            pkgs.spdlog
            pkgs.fmt
            pkgs.doxygen

            (with pkgs.rosPackages.jazzy; buildEnv {
              paths = [
                desktop
                xacro
                ros-gz-bridge

                rqt
                rqt-common-plugins

                # Simulation
                image-transport
                compressed-image-transport
                ros-gz-sim
                gz-sim-vendor
                gz-cmake-vendor
                gz-ros2-control

                ros-gz-interfaces
                simulation-interfaces

                ros2-control
                controller-manager
                ros2-controllers
                hardware-interface

                micro-ros-msgs
                fastcdr
                realsense2-camera
                rosbridge-server

                joint-trajectory-controller
                joint-state-broadcaster
                joint-state-publisher
                joint-state-publisher-gui

                python-cmake-module

                ament-cmake
                ament-cmake-core
                ament-cmake-python
              ];
            })
          ];

          shellHook = ''
            echo -e ""
            echo -e "🛡️  \033[1;36mLucy Development Environment\033[1;0m"
            echo -e "----------------------------"
            echo -e "ROS2: $ROS_DISTRO"
            echo -e "Système: ${system}"
            echo -e "----------------------------"
          '';
        };
      });
  nixConfig = {
    extra-substituters = [ "https://ros.cachix.org" ];
    extra-trusted-public-keys = [ "ros.cachix.org-1:dSyZxI8geDCJrwgvCOHDoAfOm5sV1wCPjBkKL+38Rvo=" ];
  };
}
