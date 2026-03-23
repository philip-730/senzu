{
  description = "Senzu — Secret env sync for GCP teams";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, uv2nix, pyproject-nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        lib = pkgs.lib;
        python = pkgs.python312;

        # Load the uv workspace (reads pyproject.toml + uv.lock)
        workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

        # Overlay resolving packages from uv.lock
        overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

        # Base Python package set with build systems
        pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope (
          lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            overlay
          ]
        );

        # Frozen virtualenv for packages.default / apps.default
        senzuEnv = pythonSet.mkVirtualEnv "senzu-env" workspace.deps.default;

        # Editable overlay — senzu itself is installed as an editable package
        # REPO_ROOT must be set in the shell before this is evaluated
        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };
        editablePythonSet = pythonSet.overrideScope editableOverlay;

        # Dev virtualenv: all deps including dev extras, senzu editable
        devEnv = editablePythonSet.mkVirtualEnv "senzu-dev-env" workspace.deps.all;
      in
      {
        # Frozen distributable package — usable by Nix users who want to
        # install senzu into their environment or run it via `nix run`
        packages.default = senzuEnv;

        apps.default = {
          type = "app";
          program = "${senzuEnv}/bin/senzu";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            devEnv
            pkgs.uv
            pkgs.google-cloud-sdk
          ];

          env = {
            # Stop uv from trying to manage the venv — we already have one
            UV_NO_SYNC = "1";
            # Point uv at the Nix-managed Python so it doesn't download its own
            UV_PYTHON = "${python}/bin/python";
          };

          shellHook = ''
            unset PYTHONPATH
            export REPO_ROOT=$(git rev-parse --show-toplevel)
            echo "Senzu dev shell ready. senzu is installed in editable mode."
          '';
        };
      }
    );
}
