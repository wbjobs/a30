from __future__ import annotations

import time
from datetime import datetime

import click
import requests
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

from ..console_utils import safe_print


@click.command()
@click.option("--interval", "-i", type=int, default=5, help="Refresh interval in seconds")
@click.option("--metric", "-m", multiple=True, help="Additional metric keys to display")
@click.pass_context
def watch(ctx: click.Context, interval: int, metric: tuple) -> None:
    device_url = ctx.obj["device_url"]
    extra_metrics = list(metric)

    safe_print(f"[info]Watching device at {device_url}[/info]")
    safe_print(f"[muted]Refresh every {interval}s. Press Ctrl+C to stop.[/muted]\n")

    try:
        with Live(_make_layout(device_url, extra_metrics, {}), refresh_per_second=4) as live:
            while True:
                metrics = _fetch_metrics(device_url)
                live.update(_make_layout(device_url, extra_metrics, metrics))
                time.sleep(interval)
    except KeyboardInterrupt:
        safe_print("\n[warning]Stopped watching.[/warning]")


def _fetch_metrics(device_url: str) -> dict:
    try:
        resp = requests.get(f"{device_url}/api/metrics", timeout=5)
        if resp.ok:
            data = resp.json()
            return data.get("metrics", {})
    except requests.RequestException:
        pass
    return {}


def _make_layout(device_url: str, extra_metrics: list, metrics: dict) -> Layout:
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = f"[bold cyan]E-Ink Dashboard Watch[/bold cyan]  |  Device: {device_url}  |  {now}"
    layout["header"].update(Panel(header_text, style="cyan"))

    body_layout = Layout()
    body_layout.split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    time_table = Table(show_header=False, expand=True)
    time_table.add_column("Item", style="cyan")
    time_table.add_column("Value", style="white")
    time_table.add_row("Local Time", now)

    cpu_temp = metrics.get("cpu_temp", "N/A")
    if cpu_temp != "N/A":
        temp_str = f"{cpu_temp:.1f}C"
        if isinstance(cpu_temp, (int, float)) and cpu_temp > 70:
            temp_str = f"[red]{temp_str} WARN[/red]"
        time_table.add_row("CPU Temperature", temp_str)

    body_layout["left"].update(Panel(time_table, title="System Info", border_style="blue"))

    metric_table = Table(expand=True)
    metric_table.add_column("Metric", style="cyan")
    metric_table.add_column("Value", style="green")

    all_keys = list(metrics.keys())
    for key in extra_metrics:
        if key not in all_keys:
            all_keys.append(key)

    for key in sorted(all_keys):
        if key == "cpu_temp":
            continue
        value = metrics.get(key, "N/A")
        if isinstance(value, float):
            metric_table.add_row(key, f"{value:.2f}")
        else:
            metric_table.add_row(key, str(value))

    if not all_keys:
        metric_table.add_row("(no metrics)", "...")

    body_layout["right"].update(Panel(metric_table, title="Custom Metrics", border_style="green"))

    layout["body"].update(body_layout)

    return layout
