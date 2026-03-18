"""
swarm — unified CLI entrypoint.

  python -m cli          # same as `swarm`
  swarm --help           # after pip install -e .
"""
import typer

from cli.commands.clean import clean, scan
from cli.commands.cogs import app as cogs_app
from cli.commands.run import run
from cli.commands.status import status
from cli.console import header

app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=False,
    help="TRANSMUTE-SWARM unified CLI.",
)

# Sub-Typer groups (have multiple subcommands)
app.add_typer(cogs_app, name="cogs")

# Direct commands
app.command("run")(run)
app.command("status")(status)
app.command("scan")(scan)
app.command("clean")(clean)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    header()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
