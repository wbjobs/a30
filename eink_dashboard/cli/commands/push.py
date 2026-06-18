from __future__ import annotations

import click
import requests

from ..console_utils import safe_print


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.pass_context
def push(ctx: click.Context, config_file: str) -> None:
    device_url = ctx.obj["device_url"]

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            yaml_content = f.read()
    except Exception as e:
        safe_print(f"[error]Error reading config file: {e}[/error]")
        raise SystemExit(1)

    try:
        response = requests.put(
            f"{device_url}/api/config",
            json={"yaml": yaml_content},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        safe_print("[success]Configuration pushed successfully[/success]")
        safe_print(f"  Dashboard: {result.get('message', 'Updated')}")
    except requests.RequestException as e:
        safe_print(f"[error]Error pushing config: {e}[/error]")
        raise SystemExit(1)
