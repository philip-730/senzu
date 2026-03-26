from __future__ import annotations

import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from .config import load_config, find_config_root
from .core import (
    DiffResult,
    diff_env,
    fetch_remote_kv,
    generate_settings_source,
    pull_env,
    push_env,
    read_env_file,
    write_env_file,
)
from .exceptions import (
    ConfigNotFoundError,
    KeyCollisionWarning,
    LockNotFoundError,
    SenzuError,
)
from .formats import SecretFormat, detect_format, parse_secret, serialize_secret
from .gcp import ensure_secret_exists, fetch_secret_latest, push_secret_version
from .lock import LockData, LockEntry, load_lock, save_lock

app = typer.Typer(
    name="senzu",
    help="Secret env sync for GCP teams.",
    add_completion=False,
)
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

    for key in sorted(dr.added):
        secret, project = _lock(key)
        table.add_row(f"[green]{key}[/green]", "[green]local only[/green]", secret, project)
    for key in sorted(dr.removed):
        secret, project = _lock(key)
        table.add_row(f"[red]{key}[/red]", "[red]remote only[/red]", secret, project)
    for key in sorted(dr.changed):
        secret, project = _lock(key)
        table.add_row(f"[yellow]{key}[/yellow]", "[yellow]changed[/yellow]", secret, project)

    console.print(table)


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


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

        if not overwrite and env_path.exists():
            local_kv = read_env_file(env_path)
            local_only = {k: v for k, v in local_kv.items() if k not in merged}
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
        console.print(f"  Wrote {len(final_kv)} keys to [cyan]{env_cfg.file}[/cyan]")

    save_lock(root, lock_data)
    console.print(f"  Lock file updated: [cyan]senzu.lock[/cyan]")


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


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
            err_console.print(
                f"[yellow]Warning:[/yellow] {env_cfg.file} is empty or missing."
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
            console.print(
                f"\nPush? A new secret version will be created. "
                f"Type env name to confirm: ",
                end="",
            )
            answer = input().strip()
            if answer != env_name:
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


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


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


if __name__ == "__main__":
    app()
