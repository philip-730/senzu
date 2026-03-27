from __future__ import annotations

import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.table import Table

from ..core import read_env_file
from ..exceptions import LockNotFoundError, SenzuError
from ..formats import SecretFormat, detect_format, parse_secret, serialize_secret
from ..gcp import ensure_secret_exists, fetch_secret_latest, push_secret_version
from ..lock import LockData, LockEntry, load_lock, save_lock
from ._utils import _cfg, _root, console, err_console


def _route_keys_interactively(
    source_kv: dict[str, str],
    secrets: list,
) -> dict:
    """Prompt user to route keys to secrets. Returns {key: secret_ref}."""
    options = [s.secret for s in secrets]

    console.print("\nConfigured secrets:")
    for i, s in enumerate(secrets, 1):
        console.print(f"  {i}. {s.secret}  [dim]({s.project})[/dim]")

    hint = "/".join(str(i) for i in range(1, len(options) + 1))
    default_raw = typer.prompt(
        f"Default for all? [{hint} or name, Enter to route one-by-one]",
        default="",
    )

    def resolve(raw: str):
        raw = raw.strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(secrets):
                return secrets[idx]
            return None
        return next((s for s in secrets if s.secret == raw), None)

    if default_raw:
        ref = resolve(default_raw)
        if ref is None:
            err_console.print(f"[red]Error:[/red] Invalid choice '{default_raw}'.")
            raise typer.Exit(1)
        return {k: ref for k in source_kv}

    # Key-by-key routing
    routing: dict = {}
    console.print()
    for key, val in source_kv.items():
        masked = (val[:2] + "••••") if len(val) > 2 else "••••"
        raw = typer.prompt(f"  {key} ({masked}) [{hint}]")
        ref = resolve(raw)
        if ref is None:
            err_console.print(f"[red]Error:[/red] Invalid choice '{raw}'.")
            raise typer.Exit(1)
        routing[key] = ref
    return routing


def register(app: typer.Typer) -> None:
    @app.command("import")
    def import_cmd(
        env: str = typer.Argument(..., help="Env name (e.g. dev, prod)."),
        from_file: Optional[str] = typer.Option(None, "--from", help="Source .env file. Defaults to the file configured for this env."),
        secret: Optional[str] = typer.Option(None, "--secret", "-s", help="Target secret name from senzu.toml. Routes all keys to that secret."),
        keys: Optional[str] = typer.Option(None, "--keys", "-k", help="Comma-separated keys to import. Omit for all."),
        fmt: Optional[str] = typer.Option(None, "--format", help="Secret format: json or dotenv. Defaults to dotenv."),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
    ) -> None:
        """Import a local .env file into Secret Manager and write the lock file."""
        root = _root()
        cfg = _cfg(root)

        env_cfg = cfg.envs.get(env)
        if env_cfg is None:
            err_console.print(f"[red]Error:[/red] Unknown env '{env}'.")
            raise typer.Exit(1)

        # Resolve source file
        source_path = Path(from_file) if from_file else root / env_cfg.file
        if not source_path.exists():
            err_console.print(f"[red]Error:[/red] Source file '{source_path}' not found.")
            raise typer.Exit(1)

        source_kv = read_env_file(source_path)
        if not source_kv:
            err_console.print(f"[yellow]Warning:[/yellow] '{source_path}' is empty.")
            raise typer.Exit(0)

        # Filter keys if specified
        if keys:
            requested = [k.strip() for k in keys.split(",")]
            missing = [k for k in requested if k not in source_kv]
            if missing:
                err_console.print(f"[red]Error:[/red] Keys not in source file: {', '.join(missing)}")
                raise typer.Exit(1)
            source_kv = {k: source_kv[k] for k in requested}

        # Resolve target secret(s)
        if not env_cfg.secrets:
            err_console.print(f"[red]Error:[/red] No secrets configured for env '{env}' in senzu.toml.")
            raise typer.Exit(1)

        if secret:
            secret_ref = next((s for s in env_cfg.secrets if s.secret == secret), None)
            if secret_ref is None:
                configured = ", ".join(s.secret for s in env_cfg.secrets)
                err_console.print(
                    f"[red]Error:[/red] Secret '{secret}' not in senzu.toml for env '{env}'. "
                    f"Configured: {configured}"
                )
                raise typer.Exit(1)
            key_routing: dict = {k: secret_ref for k in source_kv}
        elif len(env_cfg.secrets) == 1:
            key_routing = {k: env_cfg.secrets[0] for k in source_kv}
        else:
            key_routing = _route_keys_interactively(source_kv, env_cfg.secrets)

        # Group keys by target secret
        groups: dict[str, list[str]] = defaultdict(list)
        ref_by_name: dict = {}
        for k, ref in key_routing.items():
            groups[ref.secret].append(k)
            ref_by_name[ref.secret] = ref

        # Validate format(s)
        for secret_name, ref in ref_by_name.items():
            resolved = fmt or ref.format or "dotenv"
            if resolved not in ("json", "dotenv"):
                err_console.print(f"[red]Error:[/red] Unknown format '{resolved}'. Use 'json' or 'dotenv'.")
                raise typer.Exit(1)

        # Fetch remote for each group now, before confirmation, so the summary is accurate
        remote_cache: dict[str, dict[str, str]] = {}
        resolved_fmt_cache: dict[str, SecretFormat] = {}
        for secret_name, group_keys in groups.items():
            ref = ref_by_name[secret_name]
            resolved_fmt_cache[secret_name] = fmt or ref.format or "dotenv"  # type: ignore[assignment]
            try:
                raw_remote = fetch_secret_latest(ref.project, ref.secret)
                remote_fmt = detect_format(raw_remote, ref.format)
                remote_cache[secret_name] = parse_secret(raw_remote, remote_fmt, ref)
            except SenzuError:
                remote_cache[secret_name] = {}  # fresh secret

        # Compute per-group diffs
        GroupDiff = tuple[list[str], list[str], list[str]]  # (new_keys, changed_keys, unchanged_keys)
        group_diffs: dict[str, GroupDiff] = {}
        total_new = 0
        total_changed = 0
        for secret_name, group_keys in groups.items():
            remote_kv = remote_cache[secret_name]
            group_kv = {k: source_kv[k] for k in group_keys}
            new_keys = [k for k in group_keys if k not in remote_kv]
            changed_keys = [k for k in group_keys if k in remote_kv and remote_kv[k] != group_kv[k]]
            unchanged_keys = [k for k in group_keys if k in remote_kv and remote_kv[k] == group_kv[k]]
            group_diffs[secret_name] = (new_keys, changed_keys, unchanged_keys)
            total_new += len(new_keys)
            total_changed += len(changed_keys)

        if total_new == 0 and total_changed == 0:
            console.print("Nothing to import — remote is already up to date.")
            raise typer.Exit(0)

        # Show diff-style summary
        console.print(f"\nImporting from [cyan]{source_path}[/cyan] → env [bold]{env}[/bold]  [dim]({env_cfg.project})[/dim]")
        import_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim", pad_edge=False)
        import_table.add_column("Key")
        import_table.add_column("Status")
        import_table.add_column("Secret")
        import_table.add_column("Project")
        for secret_name, (new_keys, changed_keys, unchanged_keys) in group_diffs.items():
            ref = ref_by_name[secret_name]
            for k in sorted(new_keys):
                import_table.add_row(f"[green]{k}[/green]", "[green]new[/green]", secret_name, ref.project)
            for k in sorted(changed_keys):
                import_table.add_row(f"[yellow]{k}[/yellow]", "[yellow]changed[/yellow]", secret_name, ref.project)
            for k in sorted(unchanged_keys):
                import_table.add_row(f"[dim]{k}[/dim]", "[dim]unchanged[/dim]", f"[dim]{secret_name}[/dim]", f"[dim]{ref.project}[/dim]")
        console.print(import_table)

        if not force:
            secrets_list = ", ".join(f"[cyan]{n}[/cyan]" for n in groups)
            console.print(f"\nThis will create new version(s) of {secrets_list}. Proceed? [y/N] ", end="")
            answer = input().strip().lower()
            if answer != "y":
                console.print("Aborted.")
                raise typer.Exit(0)

        # Load lock once before pushing
        lock_data: LockData = {}
        try:
            lock_data = load_lock(root)
        except LockNotFoundError:
            pass

        env_lock = lock_data.get(env, {})

        # Push each group to its target secret (reuse cached remote data)
        for secret_name, group_keys in groups.items():
            ref = ref_by_name[secret_name]
            resolved_fmt: SecretFormat = resolved_fmt_cache[secret_name]
            group_kv = {k: source_kv[k] for k in group_keys}
            remote_kv = remote_cache[secret_name]

            merged_kv = {**remote_kv, **group_kv}

            try:
                ensure_secret_exists(ref.project, ref.secret)
                payload = serialize_secret(merged_kv, resolved_fmt)
                push_secret_version(ref.project, ref.secret, payload)
            except SenzuError as exc:
                err_console.print(f"[red]Error:[/red] {exc}")
                raise typer.Exit(1)

            new_keys, changed_keys, _ = group_diffs[secret_name]
            for key in group_keys:
                env_lock[key] = LockEntry(
                    secret=ref.secret,
                    project=ref.project,
                    format=resolved_fmt,
                    type=ref.type,
                )
            console.print(
                f"  Pushed to [cyan]{ref.secret}[/cyan]: "
                + ", ".join(filter(None, [
                    f"[green]{len(new_keys)} new[/green]" if new_keys else "",
                    f"[yellow]{len(changed_keys)} changed[/yellow]" if changed_keys else "",
                ]))
            )

        lock_data[env] = env_lock
        save_lock(root, lock_data)
        console.print(f"  Lock file updated: [cyan]senzu.lock[/cyan]")
