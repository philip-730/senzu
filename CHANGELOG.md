# Changelog

## [0.3.0](https://github.com/philip-730/senzu/compare/v0.2.0...v0.3.0) (2026-03-28)


### Features

* **cli:** add --version / -V flag ([8e839b3](https://github.com/philip-730/senzu/commit/8e839b38ef700d1c3ee181f7a772a0ed2c6ec08f))
* improve usability with pull breakdown, push safety, and status sync state ([5f1fa1f](https://github.com/philip-730/senzu/commit/5f1fa1f97943144796d55f70bfc5d5b3bea57ff1))


### Bug Fixes

* move project.urls after dependencies in pyproject.toml ([5199ea9](https://github.com/philip-730/senzu/commit/5199ea990d528e904b4cb1bfcb8362025fe2fab2))


### Documentation

* add GitHub badges to README ([a4d5b9e](https://github.com/philip-730/senzu/commit/a4d5b9e4577a737a4ad15221602915735eea4d2c))
* **readme:** update install section for PyPI ([55a6de8](https://github.com/philip-730/senzu/commit/55a6de8e8264d1eea82d718c74d83d18b9db15be))

## [0.2.0](https://github.com/philip-730/senzu/compare/v0.1.0...v0.2.0) (2026-03-26)


### Features

* show GCP project name in pull, push, and import output ([6e1047f](https://github.com/philip-730/senzu/commit/6e1047f5eb883b0477e0c399b91780b4c1c86578))
* show project/secret in tables for diff, push, and import output ([fd08dc3](https://github.com/philip-730/senzu/commit/fd08dc3c98769406ef053d27e940961a569bb3c0))


### Bug Fixes

* distinguish first pull from update, simplify push confirmation ([645b80a](https://github.com/philip-730/senzu/commit/645b80a6bb439cb4f0d6f4734ac844045bac1b33))
* flag untracked local-only keys in diff output ([9c964b3](https://github.com/philip-730/senzu/commit/9c964b363cb14c203706dc70915440ac5295e834))
* pull preserves local-only keys, import shows accurate diff, init supports flags ([c48da77](https://github.com/philip-730/senzu/commit/c48da7772211828b30fc78afc70e485ccddc4096))


### Documentation

* update README for pull merge behavior, import diff preview, init flags ([0969cdc](https://github.com/philip-730/senzu/commit/0969cdcc1d24333e25b7028c74d34aefdabe4fdf))

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
