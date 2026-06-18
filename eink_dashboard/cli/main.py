from __future__ import annotations

import os

import click

from .commands.push import push
from .commands.pull import pull
from .commands.watch import watch

DEFAULT_DEVICE_URL = os.environ.get("EINK_DEVICE_URL", "http://localhost:5000")


@click.group()
@click.option("--device-url", default=DEFAULT_DEVICE_URL, help="Device API base URL")
@click.pass_context
def cli(ctx: click.Context, device_url: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["device_url"] = device_url


@click.group()
def dashboard() -> None:
    pass


cli.add_command(dashboard)
dashboard.add_command(push)
dashboard.add_command(pull)
dashboard.add_command(watch)


if __name__ == "__main__":
    cli()
