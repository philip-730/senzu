# Changelog

## 0.1.0 (2026-03-24)


### Features

* make google-cloud-sdk optional in devShell ([c2bcf25](https://github.com/philip-730/senzu/commit/c2bcf25754217a34bea14bc4f9dcd67db2183081))


### Bug Fixes

* deduplicate uv2nix in flake inputs ([bb64e2b](https://github.com/philip-730/senzu/commit/bb64e2bc5722c1d9dbd2a2990686188d749c22cd))
* lowercase merged keys in SecretManagerSettingsSource to fix field required errors ([cb070b0](https://github.com/philip-730/senzu/commit/cb070b0398d1d2166d43e75344fb397fa3bb58cb))
* rename secrets_settings to file_secret_settings for pydantic-settings &gt;=2.4 ([0c6d2af](https://github.com/philip-730/senzu/commit/0c6d2afa2ae9465d13df39291bc4382f1ea90798))
* replace custom _DotEnv with DotEnvSettingsSource to fix field required errors ([74c825f](https://github.com/philip-730/senzu/commit/74c825f4074fd80babc3b5dcb171e062962ea251))
* wire editables into hatchling editable build inputs ([2dd99fa](https://github.com/philip-730/senzu/commit/2dd99fa4950d6151f1ed22815925179a5d1382de))


### Documentation

* add Secret Manager source JSON to nested JSON example ([9fc65bc](https://github.com/philip-730/senzu/commit/9fc65bc14342f94cdb12614ca856dc7f84bdeb81))
* expand type=raw docs to cover JSON objects, fix nested JSON wording ([aff6417](https://github.com/philip-730/senzu/commit/aff64171a2b78526a0de6136665d3fa00b41aedc))
* fill in README gaps — status, all-envs behavior, cross-project secrets, nested JSON ([a259bb5](https://github.com/philip-730/senzu/commit/a259bb55bd48d9f96f17c98f10c44f685f476a6d))
