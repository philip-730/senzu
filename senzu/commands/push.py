from __future__ import annotations

import warnings
from typing import Optional

import typer

from ..core import DiffResult, diff_env, fetch_remote_kv, push_env, read_env_file
from ..exceptions import LockNotFoundError, SenzuError
from ..lock import load_lock
from ._utils import _cfg, _print_diff, _root, console, err_console


def register(app: typer.Typer) -> None:
    @app.command()
    def push(
        env: Optional[str] = typer.Argument(None, help="Env name (e.g. dev, prod)."),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation and drift check."),
    ) -> None:
        """Push local .env changes back to Secret Manager."""
        root = _root()
        cfg = _cfg(root)

        env_names = [env] if env else list(cfg.envs.keys())

        try:
            lock_data = load_lock(root)
        except LockNotFoundError as exc:
            err_console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)

        for env_name in env_names:
            env_cfg = cfg.envs.get(env_name)
            if env_cfg is None:
                err_console.print(f"[red]Error:[/red] Unknown env '{env_name}'.")
                raise typer.Exit(1)

            lock_entries = lock_data.get(env_name, {})
            if not lock_entries:
                err_console.print(
                    f"[red]Error:[/red] No lock entries for '{env_name}'. "
                    "Run `senzu pull` first."
                )
                raise typer.Exit(1)

            env_path = root / env_cfg.file
            local_kv = read_env_file(env_path)

            if not local_kv:
                if not force:
                    err_console.print(
                        f"[red]Error:[/red] {env_cfg.file} is empty or missing. "
                        "Use --force to push an empty file and clear all secrets."
                    )
                    raise typer.Exit(1)
                err_console.print(
                    f"[yellow]Warning:[/yellow] {env_cfg.file} is empty or missing. Pushing empty secret."
                )

            console.print(f"\nPushing [bold]{env_name}[/bold]  [dim]({env_cfg.project})[/dim]")
            console.print(f"Comparing local [cyan]{env_cfg.file}[/cyan] with remote...")

            try:
                remote_kv = fetch_remote_kv(env_cfg)
            except SenzuError as exc:
                err_console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(1)

            overall_diff = diff_env(local_kv, remote_kv)

            if not overall_diff.has_drift:
                console.print("No changes detected. Remote is already up to date.")
                continue

            # Check if remote has things local doesn't (drift protection)
            if not force and overall_diff.removed:
                console.print(
                    "\n[yellow]⚠ Remote has changes not in your local file:[/yellow]\n"
                )
                _print_diff(DiffResult({}, overall_diff.removed, overall_diff.changed), lock_entries)
                console.print(
                    "\n[yellow]Blocked.[/yellow] "
                    "Run `senzu pull` to sync first, or use --force to override."
                )
                raise typer.Exit(1)

            _print_diff(overall_diff, lock_entries)

            # Confirmation prompt
            if not force:
                console.print(f"\nPush to [bold]{env_name}[/bold]? A new secret version will be created. [y/N] ", end="")
                answer = input().strip().lower()
                if answer != "y":
                    console.print("Aborted.")
                    raise typer.Exit(0)

            with warnings.catch_warnings(record=True):
                try:
                    results = push_env(env_cfg, local_kv, lock_entries, root)
                except SenzuError as exc:
                    err_console.print(f"[red]Error:[/red] {exc}")
                    raise typer.Exit(1)

            for secret_name, dr in results.items():
                if dr.has_drift:
                    console.print(f"  Pushed new version of [cyan]{secret_name}[/cyan].")
                else:
                    console.print(f"  [dim]{secret_name} — no changes, skipping.[/dim]")
