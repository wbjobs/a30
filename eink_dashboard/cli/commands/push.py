from __future__ import annotations

import click
import requests
from rich.table import Table

from eink_dashboard.config.device_manager import DeviceManager
from eink_dashboard.utils.console import console, safe_print


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--group", "-g", help="Push to device group (e.g., 'all', 'office')")
@click.option("--device", "-d", help="Push to specific device name")
@click.option("--refresh/--no-refresh", default=True, help="Refresh display after push")
@click.option("--full-refresh/--partial-refresh", default=False, help="Force full refresh")
@click.pass_context
def push(ctx: click.Context, config_file: str, group: str, device: str, refresh: bool, full_refresh: bool) -> None:
    """Push configuration to device(s).

    If --group or --device is specified, pushes to multiple devices from your device list.
    Otherwise, pushes to the device URL specified by --device-url.
    """
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            yaml_content = f.read()
    except Exception as e:
        safe_print(f"[error]Error reading config file: {e}[/error]")
        raise SystemExit(1)

    if group or device:
        _push_to_group(ctx, yaml_content, group, device, refresh, full_refresh)
    else:
        device_url = ctx.obj["device_url"]
        _push_to_single(device_url, yaml_content, refresh, full_refresh)


def _push_to_single(device_url: str, yaml_content: str, refresh: bool, full_refresh: bool) -> None:
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

        if refresh:
            endpoint = "/api/render-full" if full_refresh else "/api/render"
            try:
                requests.post(f"{device_url}{endpoint}", timeout=10)
                refresh_type = "full" if full_refresh else "partial"
                safe_print(f"  Display refreshed ({refresh_type})")
            except requests.RequestException as e:
                safe_print(f"  [warning]Warning: Could not refresh display: {e}[/warning]")

    except requests.RequestException as e:
        safe_print(f"[error]Error pushing config: {e}[/error]")
        raise SystemExit(1)


def _push_to_group(
    ctx: click.Context,
    yaml_content: str,
    group: str,
    device_name: str,
    refresh: bool,
    full_refresh: bool,
) -> None:
    manager = DeviceManager()

    if device_name:
        dev = manager.get_device(device_name)
        if dev is None:
            safe_print(f"[error]Device '{device_name}' not found[/error]")
            raise SystemExit(1)
        devices = [dev]
    else:
        devices = manager.get_devices_by_group(group or "all")

    if not devices:
        group_name = group or "all"
        safe_print(f"[warning]No devices found for group '{group_name}'[/warning]")
        raise SystemExit(1)

    safe_print(f"[info]Pushing to {len(devices)} device(s)...[/info]")
    results = manager.broadcast_push(group or "all", yaml_content)

    if refresh and results["success"] > 0:
        manager.broadcast_refresh(group or "all", full_refresh=full_refresh)

    table = Table(title="Push Results")
    table.add_column("Device", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Details", style="muted")

    for dev_name, result in sorted(results["devices"].items()):
        if result["status"] == "success":
            style = "green"
            status = "OK"
            details = result.get("message", "Updated")
        else:
            style = "red"
            status = "FAILED"
            details = result.get("error", "Unknown error")

        table.add_row(
            dev_name,
            f"[{style}]{status}[/{style}]",
            details,
        )

    console.print(table)

    summary = f"[success]{results['success']}[/success] succeeded, [error]{results['failed']}[/error] failed"
    safe_print(f"\nTotal: {results['total']} device(s) | {summary}")

    if results["failed"] > 0:
        raise SystemExit(1)
