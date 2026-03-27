from __future__ import annotations

import typer
from rich.table import Table

from ._utils import _cfg, _root, console


def register(app: typer.Typer) -> None:
    @app.command()
    def status() -> None:
        """Show all envs, GCP projects, secrets, and whether local files exist."""
        root = _root()
        cfg = _cfg(root)

        table = Table(title="Senzu Status", show_lines=True)
        table.add_column("Env", style="bold")
        table.add_column("GCP Project")
        table.add_column("Secret")
        table.add_column("Local File")
        table.add_column("File Exists")

        for env_name, env_cfg in cfg.envs.items():
            env_path = root / env_cfg.file
            file_exists = "[green]yes[/green]" if env_path.exists() else "[red]no[/red]"
            for i, secret_ref in enumerate(env_cfg.secrets):
                table.add_row(
                    env_name if i == 0 else "",
                    secret_ref.project,
                    secret_ref.secret,
                    env_cfg.file if i == 0 else "",
                    file_exists if i == 0 else "",
                )
            if not env_cfg.secrets:
                table.add_row(env_name, env_cfg.project, "(none)", env_cfg.file, file_exists)

        console.print(table)
