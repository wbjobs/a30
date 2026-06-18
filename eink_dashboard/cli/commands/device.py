from __future__ import annotations

import click
from rich.table import Table

from eink_dashboard.config.device_manager import DeviceManager
from eink_dashboard.utils.console import console, safe_print


@click.group()
def device() -> None:
    """Manage e-ink devices and groups."""
    pass


@device.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--group", "-g", multiple=True, help="Add to group (can be used multiple times)")
@click.option("--description", "-d", default="", help="Device description")
def device_add(name: str, url: str, group: tuple, description: str) -> None:
    """Add a new device."""
    manager = DeviceManager()
    try:
        groups = list(group) if group else ["all"]
        device = manager.add_device(name, url, groups=groups, description=description)
        safe_print(f"[success]Added device '{device.name}' ({device.url})[/success]")
    except ValueError as e:
        safe_print(f"[error]{e}[/error]")
        raise SystemExit(1)


@device.command("remove")
@click.argument("name")
def device_remove(name: str) -> None:
    """Remove a device."""
    manager = DeviceManager()
    try:
        manager.remove_device(name)
        safe_print(f"[success]Removed device '{name}'[/success]")
    except ValueError as e:
        safe_print(f"[error]{e}[/error]")
        raise SystemExit(1)


@device.command("list")
@click.option("--group", "-g", help="Filter by group")
@click.option("--check-status/--no-check-status", default=True, help="Check online status")
def device_list(group: str, check_status: bool) -> None:
    """List all devices with status."""
    manager = DeviceManager()

    if group:
        devices = manager.get_devices_by_group(group)
    else:
        devices = list(manager.devices.values())

    if not devices:
        safe_print("[muted]No devices configured.[/muted]")
        return

    if check_status:
        for dev in devices:
            manager.check_status(dev)

    table = Table(title="Devices")
    table.add_column("Name", style="cyan")
    table.add_column("URL", style="white")
    table.add_column("Groups", style="yellow")
    table.add_column("Status", style="white")
    table.add_column("Battery", style="green")
    table.add_column("Description", style="muted")

    for dev in devices:
        status_style = "green" if dev.online else "red"
        status = "Online" if dev.online else "Offline"
        if dev.error and not dev.online:
            status = f"Error: {dev.error[:20]}"

        battery = "N/A"
        if dev.battery_level is not None:
            battery = f"{dev.battery_level:.0f}%"
            if dev.battery_level < 20:
                battery = f"[red]{battery}[/red]"

        groups_str = ", ".join(dev.groups)

        table.add_row(
            dev.name,
            dev.url,
            groups_str,
            f"[{status_style}]{status}[/{status_style}]",
            battery,
            dev.description,
        )

    console.print(table)

    if check_status:
        online = sum(1 for d in devices if d.online)
        safe_print(f"\n[info]{online}/{len(devices)} devices online[/info]")


@device.command("status")
@click.argument("name")
def device_status(name: str) -> None:
    """Show detailed status of a device."""
    manager = DeviceManager()
    dev = manager.get_device(name)
    if dev is None:
        safe_print(f"[error]Device '{name}' not found[/error]")
        raise SystemExit(1)

    manager.check_status(dev)

    table = Table(title=f"Device: {name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Name", dev.name)
    table.add_row("URL", dev.url)
    table.add_row("Groups", ", ".join(dev.groups))
    table.add_row("Description", dev.description or "-")
    table.add_row("Timeout", f"{dev.timeout}s")

    status = "Online" if dev.online else "Offline"
    status_style = "green" if dev.online else "red"
    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")

    if dev.error:
        table.add_row("Error", dev.error)

    if dev.battery_level is not None:
        batt_str = f"{dev.battery_level:.0f}%"
        if dev.battery_level < 20:
            batt_str = f"[red]{batt_str}[/red]"
        table.add_row("Battery", batt_str)

    if dev.last_metrics:
        table.add_row("Metrics", f"{len(dev.last_metrics)} items")

    if dev.last_check:
        from datetime import datetime
        table.add_row("Last Check", datetime.fromtimestamp(dev.last_check).strftime("%H:%M:%S"))

    console.print(table)

    if dev.last_metrics:
        metric_table = Table(title="Latest Metrics")
        metric_table.add_column("Metric", style="cyan")
        metric_table.add_column("Value", style="green")
        for key, value in sorted(dev.last_metrics.items()):
            if isinstance(value, float):
                metric_table.add_row(key, f"{value:.2f}")
            else:
                metric_table.add_row(key, str(value))
        console.print(metric_table)


@device.command("groups")
def device_groups() -> None:
    """List all device groups."""
    manager = DeviceManager()
    groups = manager.list_groups()

    if not groups:
        safe_print("[muted]No groups defined.[/muted]")
        return

    table = Table(title="Device Groups")
    table.add_column("Group", style="cyan")
    table.add_column("Devices", style="white")

    for group in groups:
        devs = manager.get_devices_by_group(group)
        table.add_row(group, f"{len(devs)} device(s)")

    console.print(table)
