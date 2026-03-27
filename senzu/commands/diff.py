from __future__ import annotations

from typing import Optional

import typer

from ..core import diff_env, fetch_remote_kv, read_env_file
from ..exceptions import LockNotFoundError, SenzuError
from ..lock import LockData, load_lock
from ._utils import _cfg, _print_diff, _root, console, err_console


def register(app: typer.Typer) -> None:
    @app.command()
    def diff(
        env: Optional[str] = typer.Argument(None, help="Env name. Omit for all."),
    ) -> None:
        """Show differences between local .env files and Secret Manager. Never writes."""
        root = _root()
        cfg = _cfg(root)

        env_names = [env] if env else list(cfg.envs.keys())
        has_any_drift = False

        lock_data: LockData = {}
        try:
            lock_data = load_lock(root)
        except LockNotFoundError:
            pass

        for env_name in env_names:
            env_cfg = cfg.envs.get(env_name)
            if env_cfg is None:
                err_console.print(f"[red]Error:[/red] Unknown env '{env_name}'.")
                raise typer.Exit(1)

            env_path = root / env_cfg.file
            local_kv = read_env_file(env_path)

            try:
                remote_kv = fetch_remote_kv(env_cfg)
            except SenzuError as exc:
                err_console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(1)

            dr = diff_env(local_kv, remote_kv)
            lock_entries = lock_data.get(env_name, {})

            console.print(f"\n[bold]{env_name}[/bold]  [dim]({env_cfg.project})[/dim]  {env_cfg.file}")
            if not dr.has_drift:
                console.print("  [dim]No differences.[/dim]")
            else:
                has_any_drift = True
                _print_diff(dr, lock_entries)

        if has_any_drift:
            raise typer.Exit(1)
