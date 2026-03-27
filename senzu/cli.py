from __future__ import annotations

import typer

from .commands import diff, generate, import_cmd, init, pull, push, status

app = typer.Typer(
    name="senzu",
    help="Secret env sync for GCP teams.",
    add_completion=False,
)

pull.register(app)
push.register(app)
diff.register(app)
status.register(app)
init.register(app)
generate.register(app)
import_cmd.register(app)

if __name__ == "__main__":
    app()
