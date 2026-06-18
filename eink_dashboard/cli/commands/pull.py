from __future__ import annotations

import json
from datetime import datetime

import click
import requests
from rich.table import Table

from eink_dashboard.utils.console import console, safe_print


@click.command()
@click.option("--output", "-o", type=click.Path(), help="Output JSON file path")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="json")
@click.pass_context
def pull(ctx: click.Context, output: str, fmt: str) -> None:
    device_url = ctx.obj["device_url"]

    try:
        state_resp = requests.get(f"{device_url}/api/state", timeout=10)
        state_resp.raise_for_status()
        state = state_resp.json()
    except requests.RequestException as e:
        safe_print(f"[error]Error fetching state: {e}[/error]")
        raise SystemExit(1)

    try:
        metrics_resp = requests.get(f"{device_url}/api/metrics", timeout=10)
        metrics_resp.raise_for_status()
        metrics_data = metrics_resp.json()
        metrics = metrics_data.get("metrics", {})
    except requests.RequestException:
        metrics = {}

    data = {
        "timestamp": datetime.now().isoformat(),
        "state": state,
        "metrics": metrics,
    }

    if fmt == "table":
        _print_table(state, metrics)
    else:
        safe_print(json.dumps(data, indent=2, ensure_ascii=False))

    if output:
        try:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            safe_print(f"\n[success]Saved to {output}[/success]")
        except Exception as e:
            safe_print(f"\n[error]Error saving file: {e}[/error]")


def _print_table(state: dict, metrics: dict) -> None:
    table = Table(title="E-Ink Dashboard State")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Name", state.get("name", "N/A"))
    table.add_row("Resolution", f"{state.get('width', '?')}x{state.get('height', '?')}")
    table.add_row("Refresh Interval", f"{state.get('refresh_interval', '?')}s")
    table.add_row("Widgets", str(state.get("widget_count", 0)))

    last_render = state.get("last_render_time")
    if last_render:
        table.add_row("Last Render", datetime.fromtimestamp(last_render).strftime("%H:%M:%S"))
    else:
        table.add_row("Last Render", "Never")

    console.print(table)

    if metrics:
        metric_table = Table(title="Current Metrics")
        metric_table.add_column("Metric", style="cyan")
        metric_table.add_column("Value", style="green")
        for key, value in sorted(metrics.items()):
            if isinstance(value, float):
                metric_table.add_row(key, f"{value:.2f}")
            else:
                metric_table.add_row(key, str(value))
        console.print(metric_table)
