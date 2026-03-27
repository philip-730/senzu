# senzu

[![PyPI version](https://img.shields.io/pypi/v/senzu)](https://pypi.org/project/senzu/)
[![CI](https://github.com/philip-730/senzu/actions/workflows/ci.yml/badge.svg)](https://github.com/philip-730/senzu/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/senzu)](https://pypi.org/project/senzu/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI downloads](https://img.shields.io/pypi/dm/senzu)](https://pypi.org/project/senzu/)
[![codecov](https://codecov.io/gh/philip-730/senzu/branch/main/graph/badge.svg)](https://codecov.io/gh/philip-730/senzu)

Stop manually copy-pasting secrets from GCP Secret Manager into `.env` files like an animal. Senzu syncs secrets between GCP Secret Manager and local `.env` files, tracks where every key came from, and won't let you blow up production by pushing stale local changes over remote ones.

It's a CLI + Python library for teams using GCP Secret Manager who need their secrets to actually stay in sync — across multiple environments, multiple secrets, multiple people.

---

## Why it's actually sick

Most teams end up with a shared `.env` in a private Slack channel, a Notion doc, or some other nightmare. If you're using Secret Manager, you're at least in the right place — but the workflow is still garbage. You open the GCP console, copy values one by one, paste them into a file you hope you don't accidentally commit.

Senzu fixes this:

- **`senzu pull`** — fetches all your configured secrets into a local `.env` file in one command. Handles JSON and dotenv formats automatically. Works across multiple secrets per environment. If your local file already has keys that aren't in remote yet, they're preserved — remote wins on conflicts, but local-only keys survive. Use `--overwrite` if you want the remote to fully replace your local file.

- **`senzu push`** — pushes local changes back to Secret Manager. But here's the thing: it actually checks if someone else changed the remote since you last pulled. If they did, it blocks you.
- **`senzu diff`** — see exactly what's different between your local file and what's in Secret Manager, without touching anything. Pipe it into CI, use it in code review, whatever.

- **Lock file** — after a pull, Senzu writes `senzu.lock` which tracks which key came from which secret and which project. This is what makes push safe. It knows exactly where to send each key back, even if you're pulling from 5 different secrets into one `.env`.

- **`senzu import`** — already have a `.env` file and want to get into Secret Manager without touching the GCP console? `senzu import dev --from .env` creates the secret if it doesn't exist, pushes the keys, and writes `senzu.lock` so you're immediately ready to pull/push. If the secret already has data, it merges — your local keys win. Before confirming, it shows you exactly which keys are new, which are changed, and which are unchanged, so you know what you're actually pushing. If nothing has changed, it exits early.

- **Multiple environments** — `dev`, `staging`, `prod`, whatever you want. Each one can have its own GCP project, its own secrets, its own local file. `senzu pull dev` or `senzu pull prod`, no config flags needed.

- **`SenzuSettings`** — drop-in Pydantic BaseSettings subclass. Automatically reads the right `.env` file based on your `ENV` var, parses nested JSON objects into proper Python dicts/lists, and falls back to reading directly from Secret Manager in Cloud Run by just setting `SENZU_USE_SECRET_MANAGER=true`.

- **`senzu generate`** — auto-generates a typed Pydantic settings class from your actual secrets. You never have to manually write `api_key: str` for every field again.

---

## Install

Senzu isn't on PyPI yet. Install directly from GitHub:

```bash
pip install git+https://github.com/philip-730/senzu
# or
uv add git+https://github.com/philip-730/senzu
```

Pin to a specific commit or tag if you need stability:

```bash
pip install git+https://github.com/philip-730/senzu@v0.1.0
```

To add it to `requirements.txt`:

```
senzu @ git+https://github.com/philip-730/senzu
# or pinned:
senzu @ git+https://github.com/philip-730/senzu@v0.1.0
```

Requires Python 3.10+. You'll need GCP credentials set up — either `gcloud auth application-default login` locally or a service account in prod.

---

## Setup

Run the init wizard in your project root:

```bash
senzu init

# or skip the prompts entirely with flags
senzu init --project my-gcp-project --env dev --file .env.dev --secret app-env
```

This creates `senzu.toml` and updates `.gitignore` to exclude your `.env.*` files. You don't want those committed. The `--env` flag controls the environment name (defaults to `dev`) — useful if you want to scaffold a non-dev env first.

Or write `senzu.toml` yourself:

```toml
[envs.dev]
project = "my-gcp-project-dev"
file    = ".env.dev"
secrets = [
  { secret = "app-env" },
  { secret = "db-creds", format = "json" },
]

[envs.prod]
project = "my-gcp-project-prod"
file    = ".env.prod"
secrets = [
  { secret = "app-env-prod" },
]
```

Each secret in the `secrets` array is fetched and merged into the local file. If you want the entire secret stored as a single env var rather than expanded into individual keys, use `type = "raw"`. `env_var` is required — it sets the env var name the value is written under:

```toml
secrets = [
  # Scalar value (e.g. a webhook secret string)
  { secret = "stripe-webhook-secret", type = "raw", env_var = "STRIPE_WEBHOOK_SECRET" },

  # JSON object stored whole — useful when you want one dict, not individual keys
  { secret = "firebase-sdk", type = "raw", env_var = "FIREBASE_CREDS" },
]
```

For the JSON case, Senzu stores it single-quoted in the `.env` file (`FIREBASE_CREDS='{"type":"service_account",...}'`). Declare the field as `dict` in `SenzuSettings` and it's automatically deserialized.

### Cross-project secrets

A secret can pull from a different GCP project than the environment default. This is useful for shared infrastructure secrets owned by a central project:

```toml
[envs.prod]
project = "my-app-prod"
file    = ".env.prod"
secrets = [
  { secret = "app-env-prod" },
  { secret = "datadog-api-key", project = "shared-infra" },
]
```

When multiple secrets share a key name, the last secret listed wins. Senzu will emit a warning so you know it happened.

---

## Usage

```bash
# Bootstrap — import an existing .env into Secret Manager for the first time
senzu import dev --from .env
senzu import dev --from .env --secret app-env          # skip interactive routing, send all keys to this secret
senzu import dev --from .env --keys DB_URL,DB_PASSWORD # specific keys only
senzu import dev --from .env --format json             # write as JSON instead of dotenv

# Pull secrets to local .env files
senzu pull              # all environments defined in senzu.toml
senzu pull dev          # specific environment only
senzu pull dev --overwrite  # fully replace local file with remote (discards local-only keys)

# See what's different between local and remote
senzu diff         # all environments
senzu diff dev     # specific environment only

# Push local changes back to Secret Manager
senzu push         # all environments (prompts for confirmation per env)
senzu push dev     # specific environment
senzu push dev --force  # skip confirmation even if remote has unretrieved changes

# Show all configured environments, their secrets, GCP projects, and local file status
senzu status

# Generate a typed Pydantic settings class from your secrets
senzu generate dev --out settings.py
```

---

## Using in Python

If you have a Python app and want type-safe settings without the manual config:

```python
from senzu import SenzuSettings

class Settings(SenzuSettings):
    database_url: str
    api_key: str
    firebase_creds: dict  # see note on nested JSON below

settings = Settings()
```

GCP secrets often store nested JSON objects (service account keys, connection configs, etc.) that can't be written as raw dotenv values. Senzu encodes these as single-quoted strings in the `.env` file:

```json
// Secret Manager — app-env secret value
{
  "database_url": "postgres://...",
  "api_key": "sk-...",
  "firebase_creds": { "type": "service_account", "project_id": "my-app" }
}
```

```bash
# .env.dev — what Senzu writes after senzu pull
DATABASE_URL=postgres://...
API_KEY=sk-...
FIREBASE_CREDS='{"type":"service_account","project_id":"my-app"}'
```

When you declare the field as `dict` (or `list`) in `SenzuSettings`, Senzu automatically deserializes it — so `settings.firebase_creds` is already a Python dict, not a string.

Senzu reads `ENV` or `SENZU_ENV` to figure out which environment you're in, finds the right `.env` file from `senzu.toml`, and loads it. In Cloud Run or any environment where you don't have a file, set `SENZU_USE_SECRET_MANAGER=true` and it reads directly from Secret Manager.

---

## The lock file

After `senzu pull`, you'll have a `senzu.lock` file. This is how Senzu knows which of your 40 env vars came from which of your 5 secrets. Don't delete it — push won't work without it. Commit it — it contains no secret values, just routing metadata (which key lives in which secret), and your teammates need it to push without doing a redundant pull first.

---

## Auth

Senzu uses the standard GCP auth chain via `google-cloud-secret-manager`. Locally, run:

```bash
gcloud auth application-default login
```

In CI/CD or Cloud Run, use a service account with `Secret Manager Secret Accessor` role on the relevant secrets.

---

## Development

### With Nix (recommended)

The repo uses [uv2nix](https://github.com/pyproject-nix/uv2nix) to provide a fully reproducible dev environment. Dependencies are pinned in `uv.lock`.

```bash
nix develop
```

This drops you into a shell with the right Python version, all deps installed, and senzu itself available as an editable install — changes to the source are reflected immediately without reinstalling. `gcloud` is also available.

To run the CLI directly without entering a shell:

```bash
nix run
```

### Without Nix

```bash
uv sync
uv run senzu --help
```

Or with a standard virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Running tests

```bash
pytest
# or inside nix develop:
pytest tests/
```
