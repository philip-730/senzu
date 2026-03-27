from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ._utils import console


def register(app: typer.Typer) -> None:
    @app.command()
    def init(
        project: Optional[str] = typer.Option(None, "--project", help="GCP project ID."),
        file: Optional[str] = typer.Option(None, "--file", help="Local .env file path."),
        secret: Optional[str] = typer.Option(None, "--secret", help="Secret name in Secret Manager."),
        env: str = typer.Option("dev", "--env", help="Environment name (default: dev)."),
    ) -> None:
        """Scaffold a senzu.toml interactively and update .gitignore."""
        config_path = Path("senzu.toml")
        if config_path.exists():
            console.print("[yellow]senzu.toml already exists.[/yellow] Skipping scaffold.")
        else:
            console.print(f"Let's create a [cyan]senzu.toml[/cyan] for env [bold]{env}[/bold].")
            if project is None:
                project = typer.prompt(f"GCP project ID for '{env}'")
            if file is None:
                file = typer.prompt(f"Local .env file for '{env}'", default=f".env.{env}")
            if secret is None:
                secret = typer.prompt("Secret name in Secret Manager", default="app-env")

            toml_content = f"""[envs.{env}]
project = "{project}"
file    = "{file}"
secrets = [
  {{ secret = "{secret}" }}
]

# Add more envs below, e.g.:
# [envs.prod]
# project = "my-app-prod-456"
# file    = ".env.prod"
# secrets = [
#   {{ secret = "app-env" }}
# ]
"""
            config_path.write_text(toml_content)
            console.print(f"\nCreated [cyan]senzu.toml[/cyan]:\n")
            console.print(toml_content.rstrip())
            console.print(
                f"\n[bold]Next steps:[/bold]\n"
                f"  [cyan]senzu import {env}[/cyan]   — push your local {file} to Secret Manager\n"
                f"  [cyan]senzu pull {env}[/cyan]     — fetch existing secrets from Secret Manager\n"
            )

        # Update .gitignore
        gitignore = Path(".gitignore")
        additions = [".env.*"]
        existing = gitignore.read_text() if gitignore.exists() else ""
        lines_to_add = [line for line in additions if line not in existing]
        if lines_to_add:
            with gitignore.open("a") as f:
                f.write("\n# Senzu\n")
                for line in lines_to_add:
                    f.write(f"{line}\n")
            console.print(f"Updated [cyan].gitignore[/cyan]: added {', '.join(lines_to_add)}")
        else:
            console.print(".gitignore already up to date.")
