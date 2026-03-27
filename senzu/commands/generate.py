from __future__ import annotations

from pathlib import Path

import typer

from ..core import fetch_remote_kv, generate_settings_source
from ..exceptions import SenzuError
from ._utils import _cfg, _root, console, err_console


def register(app: typer.Typer) -> None:
    @app.command()
    def generate(
        env: str = typer.Argument("dev", help="Env to generate settings from."),
        out: str = typer.Option("settings.py", "--out", "-o", help="Output file path."),
    ) -> None:
        """Generate a SenzuSettings subclass from the current secrets for an env."""
        root = _root()
        cfg = _cfg(root)

        env_cfg = cfg.envs.get(env)
        if env_cfg is None:
            err_console.print(f"[red]Error:[/red] Unknown env '{env}'.")
            raise typer.Exit(1)

        try:
            remote_kv = fetch_remote_kv(env_cfg)
        except SenzuError as exc:
            err_console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)

        out_path = Path(out)
        if out_path.exists():
            overwrite = typer.confirm(f"{out} already exists. Overwrite?", default=False)
            if not overwrite:
                console.print("Aborted.")
                raise typer.Exit(0)

        source = generate_settings_source(env, remote_kv)
        out_path.write_text(source)
        console.print(
            f"Generated [cyan]{out}[/cyan] — review before committing."
        )
