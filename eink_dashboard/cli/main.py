from __future__ import annotations

import os

import click

from eink_dashboard.cli.commands.carousel import carousel as carousel_cmd, alert as alert_cmd
from eink_dashboard.cli.commands.device import device as device_cmd
from eink_dashboard.cli.commands.generate import generate
from eink_dashboard.cli.commands.push import push
from eink_dashboard.cli.commands.pull import pull
from eink_dashboard.cli.commands.watch import watch

DEFAULT_DEVICE_URL = os.environ.get("EINK_DEVICE_URL", "http://localhost:5000")


@click.group()
@click.option("--device-url", default=DEFAULT_DEVICE_URL, help="Device API base URL")
@click.pass_context
def cli(ctx: click.Context, device_url: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["device_url"] = device_url


@click.group()
def dashboard() -> None:
    """Dashboard management commands"""
    pass


cli.add_command(dashboard)
cli.add_command(device_cmd)
cli.add_command(carousel_cmd)
cli.add_command(alert_cmd)
cli.add_command(generate, name="generate")

dashboard.add_command(push)
dashboard.add_command(pull)
dashboard.add_command(watch)

cli.add_command(push, name="push")
cli.add_command(pull, name="pull")
cli.add_command(watch, name="watch")


if __name__ == "__main__":
    cli()
