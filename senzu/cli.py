from __future__ import annotations

from typing import Optional

import typer

from . import __version__
from .commands import diff, generate, import_cmd, init, pull, push, status

app = typer.Typer(
    name="senzu",
    help="Secret env sync for GCP teams.",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"senzu {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass

pull.register(app)
push.register(app)
diff.register(app)
status.register(app)
init.register(app)
generate.register(app)
import_cmd.register(app)

if __name__ == "__main__":
    app()
