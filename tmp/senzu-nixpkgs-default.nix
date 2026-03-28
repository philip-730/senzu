{
  lib,
  buildPythonPackage,
  fetchPypi,
  hatchling,
  typer,
  rich,
  pydantic-settings,
  google-cloud-secret-manager,
  toml,
  python-dotenv,
  pytestCheckHook,
  pytest-mock,
}:

buildPythonPackage rec {
  pname = "senzu";
  version = "0.3.0";
  pyproject = true;

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-+EEaJhpw7MDVhqlOS/78REUOmab7lsoKZjz+SwDk8WQ=";
  };

  build-system = [
    hatchling
  ];

  dependencies = [
    typer
    rich
    pydantic-settings
    google-cloud-secret-manager
    toml
    python-dotenv
  ];

  nativeCheckInputs = [
    pytestCheckHook
    pytest-mock
  ];

  pythonImportsCheck = [ "senzu" ];

  meta = {
    description = "Secret env sync for GCP teams";
    homepage = "https://github.com/philip-730/senzu";
    changelog = "https://github.com/philip-730/senzu/blob/v${version}/CHANGELOG.md";
    license = lib.licenses.mit;
    maintainers = with lib.maintainers; [ philip-730 ];
    mainProgram = "senzu";
  };
}
