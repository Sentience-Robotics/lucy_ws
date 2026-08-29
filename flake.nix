{
  description = "Lucy ROS 2 workspace dev environment (Pixi + RoboStack on NixOS)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        fhs = pkgs.buildFHSEnv {
          name = "lucy-ws";
          targetPkgs = pkgs: with pkgs; [
            pixi
            git
            python3
            tmux
            cacert
          ];
          profile = ''
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            echo "Lucy dev shell — host tools from nixpkgs; ROS via Pixi (RoboStack)."
            echo "  ./install.sh          clone + pixi install + build"
            echo "  ./launch_lucy.sh      tmux + Control Center launcher"
          '';
          runScript = "bash";
        };
      in {
        devShells.default = fhs.env;
        apps.default = flake-utils.lib.mkApp {
          drv = pkgs.writeShellScriptBin "lucy-install" ''
            cd "${self}"
            exec ${fhs.env}/bin/bash -lc './install.sh "$@"'
          '';
        };
      });
}
