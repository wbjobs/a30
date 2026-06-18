from __future__ import annotations

from typing import Optional

import click
import requests
from rich.table import Table

from eink_dashboard.utils.console import console, safe_print


@click.group()
@click.pass_context
def carousel(ctx: click.Context) -> None:
    """Control carousel pages and transitions."""
    ctx.ensure_object(dict)


@carousel.command(name="status")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def status(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Get current carousel status."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.get(f"{url}/api/carousel", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        table = Table(title="Carousel Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Enabled", "Yes" if data["enabled"] else "No")
        table.add_row("Current page", data["current_page"] or "N/A")
        table.add_row("Target page", data["target_page"] or "N/A")
        table.add_row("Transitioning", "Yes" if data["is_transitioning"] else "No")
        table.add_row("Transition", data["transition"])
        table.add_row("Interval (s)", str(data["interval"]))
        table.add_row("Pages", ", ".join(data["pages"]))
        table.add_row("Default page", data["default_page"] or "N/A")

        console.print(table)

    except requests.RequestException as e:
        safe_print(f"[error]Failed to get carousel status: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="next")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def next_page(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Go to next carousel page."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.put(
            f"{url}/api/carousel",
            json={"action": "next"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        safe_print(f"[success]Switched to page: {data['page']}[/success]")
    except requests.RequestException as e:
        safe_print(f"[error]Failed to switch page: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="prev")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def prev_page(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Go to previous carousel page."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.put(
            f"{url}/api/carousel",
            json={"action": "prev"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        safe_print(f"[success]Switched to page: {data['page']}[/success]")
    except requests.RequestException as e:
        safe_print(f"[error]Failed to switch page: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="goto")
@click.argument("page_name")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def goto_page(ctx: click.Context, page_name: str, device_url: Optional[str] = None) -> None:
    """Go to specific carousel page."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.put(
            f"{url}/api/carousel",
            json={"action": "set_page", "page": page_name},
            timeout=10,
        )
        resp.raise_for_status()
        safe_print(f"[success]Switched to page: {page_name}[/success]")
    except requests.RequestException as e:
        safe_print(f"[error]Failed to switch page: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="enable")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def enable_carousel(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Enable carousel."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.put(
            f"{url}/api/carousel",
            json={"action": "toggle", "enabled": True},
            timeout=10,
        )
        resp.raise_for_status()
        safe_print("[success]Carousel enabled[/success]")
    except requests.RequestException as e:
        safe_print(f"[error]Failed to enable carousel: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="disable")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def disable_carousel(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Disable carousel."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.put(
            f"{url}/api/carousel",
            json={"action": "toggle", "enabled": False},
            timeout=10,
        )
        resp.raise_for_status()
        safe_print("[success]Carousel disabled[/success]")
    except requests.RequestException as e:
        safe_print(f"[error]Failed to disable carousel: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="transition")
@click.argument("from_page")
@click.argument("to_page")
@click.option("--output", "-o", help="Output GIF file path")
@click.option("--frames", "-n", type=int, help="Number of transition frames")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def transition(
    ctx: click.Context,
    from_page: str,
    to_page: str,
    output: Optional[str] = None,
    frames: Optional[int] = None,
    device_url: Optional[str] = None,
) -> None:
    """Generate transition animation between pages."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        data = {"from_page": from_page, "to_page": to_page}
        if frames:
            data["num_frames"] = frames

        resp = requests.post(
            f"{url}/api/carousel/transition",
            json=data,
            timeout=30,
        )
        resp.raise_for_status()

        if output:
            with open(output, "wb") as f:
                f.write(resp.content)
            safe_print(f"[success]Transition GIF saved: {output}[/success]")
        else:
            safe_print(f"[success]Transition generated ({len(resp.content)} bytes)[/success]")

    except requests.RequestException as e:
        safe_print(f"[error]Failed to generate transition: {e}[/error]")
        raise SystemExit(1)


@carousel.command(name="render")
@click.argument("page_name")
@click.option("--output", "-o", required=True, help="Output PNG file path")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def render_page(
    ctx: click.Context,
    page_name: str,
    output: str,
    device_url: Optional[str] = None,
) -> None:
    """Render specific page to image file."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.post(
            f"{url}/api/render-page",
            json={"page": page_name, "display": False},
            timeout=30,
        )
        resp.raise_for_status()

        with open(output, "wb") as f:
            f.write(resp.content)

        safe_print(f"[success]Page '{page_name}' rendered to: {output}[/success]")

    except requests.RequestException as e:
        safe_print(f"[error]Failed to render page: {e}[/error]")
        raise SystemExit(1)


@click.group()
@click.pass_context
def alert(ctx: click.Context) -> None:
    """Manage alerts and notifications."""
    ctx.ensure_object(dict)


@alert.command(name="trigger")
@click.argument("message")
@click.option("--severity", "-s", type=click.Choice(["info", "warning", "critical"]), default="warning")
@click.option("--device-url", "-u", help="Device API base URL")
@click.option("--group", "-g", help="Device group to broadcast")
@click.pass_context
def trigger_alert(
    ctx: click.Context,
    message: str,
    severity: str,
    device_url: Optional[str] = None,
    group: Optional[str] = None,
) -> None:
    """Trigger an alert on device(s)."""
    from eink_dashboard.config.device_manager import DeviceManager

    if group:
        dm = DeviceManager()
        devices = dm.get_devices_by_group(group)
        if not devices:
            safe_print(f"[error]No devices found for group '{group}'[/error]")
            raise SystemExit(1)

        results = {}
        for dev in devices:
            try:
                resp = requests.post(
                    f"{dev.url}/api/alert",
                    json={"message": message, "severity": severity},
                    timeout=5,
                )
                results[dev.name] = "success" if resp.ok else f"HTTP {resp.status_code}"
            except requests.RequestException as e:
                results[dev.name] = f"Error: {e}"

        table = Table(title=f"Alert Broadcast - {group}")
        table.add_column("Device", style="cyan")
        table.add_column("Status", style="white")

        for name, status in sorted(results.items()):
            table.add_row(name, status)

        console.print(table)

    else:
        url = device_url or ctx.obj.get("device_url")
        if not url:
            safe_print("[error]No device URL specified[/error]")
            raise SystemExit(1)

        try:
            resp = requests.post(
                f"{url}/api/alert",
                json={"message": message, "severity": severity},
                timeout=10,
            )
            resp.raise_for_status()
            safe_print(f"[success]Alert triggered: {message}[/success]")
        except requests.RequestException as e:
            safe_print(f"[error]Failed to trigger alert: {e}[/error]")
            raise SystemExit(1)


@alert.command(name="clear")
@click.option("--device-url", "-u", help="Device API base URL")
@click.option("--group", "-g", help="Device group to broadcast")
@click.pass_context
def clear_alert(
    ctx: click.Context,
    device_url: Optional[str] = None,
    group: Optional[str] = None,
) -> None:
    """Clear active alert on device(s)."""
    from eink_dashboard.config.device_manager import DeviceManager

    if group:
        dm = DeviceManager()
        devices = dm.get_devices_by_group(group)
        if not devices:
            safe_print(f"[error]No devices found for group '{group}'[/error]")
            raise SystemExit(1)

        results = {}
        for dev in devices:
            try:
                resp = requests.delete(f"{dev.url}/api/alert", timeout=5)
                results[dev.name] = "success" if resp.ok else f"HTTP {resp.status_code}"
            except requests.RequestException as e:
                results[dev.name] = f"Error: {e}"

        table = Table(title=f"Clear Alert - {group}")
        table.add_column("Device", style="cyan")
        table.add_column("Status", style="white")

        for name, status in sorted(results.items()):
            table.add_row(name, status)

        console.print(table)

    else:
        url = device_url or ctx.obj.get("device_url")
        if not url:
            safe_print("[error]No device URL specified[/error]")
            raise SystemExit(1)

        try:
            resp = requests.delete(f"{url}/api/alert", timeout=10)
            resp.raise_for_status()
            safe_print("[success]Alert cleared[/success]")
        except requests.RequestException as e:
            safe_print(f"[error]Failed to clear alert: {e}[/error]")
            raise SystemExit(1)


@alert.command(name="status")
@click.option("--device-url", "-u", help="Device API base URL")
@click.pass_context
def alert_status(ctx: click.Context, device_url: Optional[str] = None) -> None:
    """Get current alert status."""
    url = device_url or ctx.obj.get("device_url")
    if not url:
        safe_print("[error]No device URL specified[/error]")
        raise SystemExit(1)

    try:
        resp = requests.get(f"{url}/api/alert", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        table = Table(title="Alert Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Active", "Yes" if data["active"] else "No")
        if data["active"]:
            table.add_row("Message", data["message"])
            table.add_row("Severity", data["severity"])
            table.add_row("Remaining (s)", f"{data['remaining_time']:.1f}")

        console.print(table)

    except requests.RequestException as e:
        safe_print(f"[error]Failed to get alert status: {e}[/error]")
        raise SystemExit(1)
