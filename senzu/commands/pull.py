from __future__ import annotations

import warnings
from typing import Optional

import typer

from ..core import pull_env, read_env_file, write_env_file
from ..exceptions import KeyCollisionWarning, LockNotFoundError, SenzuError
from ..lock import LockData, load_lock, save_lock
from ._utils import _cfg, _root, console, err_console


def register(app: typer.Typer) -> None:
    @app.command()
    def pull(
        env: Optional[str] = typer.Argument(None, help="Env name (e.g. dev, prod). Omit for all."),
        overwrite: bool = typer.Option(
            False,
            "--overwrite",
            help="Fully replace local file with remote data, discarding local-only keys.",
        ),
    ) -> None:
        """Fetch secrets from Secret Manager and write to local .env files.

        By default, keys present only in your local file (not yet pushed to remote)
        are preserved. Use --overwrite to replace the local file entirely with remote data.
        """
        root = _root()
        cfg = _cfg(root)

        env_names = [env] if env else list(cfg.envs.keys())

        lock_data: LockData = {}
        try:
            lock_data = load_lock(root)
        except LockNotFoundError:
            pass  # first pull — no lock yet

        for env_name in env_names:
            env_cfg = cfg.envs.get(env_name)
            if env_cfg is None:
                err_console.print(f"[red]Error:[/red] Unknown env '{env_name}'.")
                raise typer.Exit(1)

            console.print(f"Pulling [bold]{env_name}[/bold]  [dim]({env_cfg.project})[/dim]...")

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", KeyCollisionWarning)
                try:
                    merged, lock_entries = pull_env(env_cfg, root)
                except SenzuError as exc:
                    err_console.print(f"[red]Error:[/red] {exc}")
                    raise typer.Exit(1)

            for w in caught:
                err_console.print(f"[yellow]Warning:[/yellow] {w.message}")

            env_path = root / env_cfg.file

            is_first_pull = not env_path.exists()
            local_kv = {} if is_first_pull else read_env_file(env_path)

            if not overwrite and not is_first_pull:
                local_only = {k: v for k, v in local_kv.items() if k not in merged}
                would_overwrite = {
                    k: (local_kv[k], merged[k])
                    for k in local_kv
                    if k in merged and local_kv[k] != merged[k]
                }

                if would_overwrite:
                    console.print(
                        f"  [yellow]Warning:[/yellow] {len(would_overwrite)} local change(s) will be overwritten by remote:"
                    )
                    for k in sorted(would_overwrite):
                        console.print(f"    [yellow]{k}[/yellow]  (local → remote)")
                    console.print("  Proceed and overwrite these local changes? \\[y/N] ", end="")
                    answer = input().strip().lower()
                    if answer != "y":
                        console.print("  Aborted.")
                        raise typer.Exit(0)

                if local_only:
                    console.print(
                        f"  [yellow]Kept {len(local_only)} local-only key(s) not in remote:[/yellow] "
                        + ", ".join(sorted(local_only))
                    )
                final_kv = {**local_only, **merged}
            else:
                final_kv = merged

            write_env_file(env_path, final_kv)
            lock_data[env_name] = lock_entries
            if is_first_pull:
                console.print(f"  Created [cyan]{env_cfg.file}[/cyan] with {len(final_kv)} keys")
            else:
                new_count = sum(1 for k in merged if k not in local_kv)
                updated_count = sum(1 for k in merged if k in local_kv and local_kv[k] != merged[k])
                removed_count = sum(1 for k in local_kv if k not in final_kv)
                parts = list(filter(None, [
                    f"[green]{new_count} new[/green]" if new_count else "",
                    f"[yellow]{updated_count} updated[/yellow]" if updated_count else "",
                    f"[red]{removed_count} removed[/red]" if removed_count else "",
                ]))
                summary = ", ".join(parts) if parts else "no changes"
                console.print(f"  Updated [cyan]{env_cfg.file}[/cyan] — {summary} ({len(final_kv)} total)")

        save_lock(root, lock_data)
        console.print(f"  Lock file updated: [cyan]senzu.lock[/cyan]")
