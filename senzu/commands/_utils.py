from __future__ import annotations

from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from ..config import find_config_root, load_config
from ..core import DiffResult
from ..exceptions import ConfigNotFoundError, SenzuError
from ..lock import LockEntry

console = Console()
err_console = Console(stderr=True)


def _root() -> Path:
    try:
        return find_config_root()
    except ConfigNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


def _cfg(root: Path):
    try:
        return load_config(root)
    except SenzuError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)


def _print_diff(dr: DiffResult, lock_entries: dict[str, LockEntry] | None = None) -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", pad_edge=False)
    table.add_column("Key")
    table.add_column("Change")
    table.add_column("Secret")
    table.add_column("Project")

    def _lock(key: str) -> tuple[str, str]:
        if lock_entries and key in lock_entries:
            e = lock_entries[key]
            return e.secret, e.project
        return "—", "—"

    untracked: list[str] = []

    for key in sorted(dr.added):
        secret, project = _lock(key)
        if secret == "—":
            untracked.append(key)
        table.add_row(f"[green]{key}[/green]", "[green]local only[/green]", secret, project)
    for key in sorted(dr.removed):
        secret, project = _lock(key)
        table.add_row(f"[red]{key}[/red]", "[red]remote only[/red]", secret, project)
    for key in sorted(dr.changed):
        secret, project = _lock(key)
        table.add_row(f"[yellow]{key}[/yellow]", "[yellow]changed[/yellow]", secret, project)

    console.print(table)

    if untracked:
        console.print(
            f"  [dim]Note: {', '.join(untracked)} "
            f"{'has' if len(untracked) == 1 else 'have'} no lock entry and will be skipped by push. "
            f"Run [/dim][cyan]senzu import[/cyan][dim] to register {'it' if len(untracked) == 1 else 'them'}.[/dim]"
        )
