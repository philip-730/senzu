{
  description = "Senzu — Secret env sync for GCP teams";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        senzu = python.pkgs.buildPythonPackage {
          pname = "senzu";
          version = "0.1.0";
          pyproject = true;

          src = ./.;

          build-system = [ python.pkgs.hatchling ];

          dependencies = with python.pkgs; [
            typer
            rich
            pydantic-settings
            google-cloud-secret-manager
            toml
            python-dotenv
          ];

          meta = {
            description = "Secret env sync for GCP teams";
            license = pkgs.lib.licenses.mit;
          };
        };
      in
      {
        packages.default = senzu;

        apps.default = {
          type = "app";
          program = "${senzu}/bin/senzu";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (ps: with ps; [
              typer
              rich
              pydantic-settings
              google-cloud-secret-manager
              toml
              python-dotenv
              pytest
              pytest-mock
              ruff
            ]))
            pkgs.google-cloud-sdk
          ];

          shellHook = ''
            echo "Senzu dev shell ready."
            echo "Run: pip install -e '.[dev]' to install in editable mode."
          '';
        };
      }
    );
}
