from __future__ import annotations

import os
from typing import Optional

import click
from rich.table import Table

from eink_dashboard.config.parser import build_context, load_config
from eink_dashboard.device.renderer import DashboardRenderer
from eink_dashboard.utils.console import console, safe_print


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--output", "-o", required=True, type=click.Path(), help="Output file path (PNG or PDF)")
@click.option("--page", "-p", multiple=True, help="Page name to generate (for carousel configs)")
@click.option("--format", "-f", "fmt", type=click.Choice(["png", "pdf", "auto"]), default="auto", help="Output format")
@click.option("--variable", "-v", multiple=True, help="Set variable: key=value")
@click.option("--dpi", type=int, default=100, help="PDF resolution (DPI)")
def generate(
    config_file: str,
    output: str,
    page: tuple,
    fmt: str,
    variable: tuple,
    dpi: int,
) -> None:
    """Generate dashboard image or PDF without a device."""
    config = load_config(config_file)

    context_vars = {}
    for var in variable:
        if "=" in var:
            key, value = var.split("=", 1)
            context_vars[key.strip()] = value.strip()

    context = build_context(config.variables, {})
    context.update(context_vars)

    renderer = DashboardRenderer(config)

    if fmt == "auto":
        ext = os.path.splitext(output)[1].lower()
        if ext == ".pdf":
            fmt = "pdf"
        else:
            fmt = "png"

    pages = list(page) if page else []

    if fmt == "pdf":
        renderer.render_to_pdf(output, pages or None, context)
        safe_print(f"[success]PDF generated: {output}[/success]")

        if config.carousel.enabled:
            page_list = pages or [p.name for p in config.carousel.pages]
            safe_print(f"  Pages: {', '.join(page_list)}")
    else:
        if config.carousel.enabled and pages:
            if len(pages) > 1:
                for i, page_name in enumerate(pages):
                    image = renderer.render_offline(page_name, context)
                    base, ext = os.path.splitext(output)
                    page_output = f"{base}_{page_name}{ext}"
                    image.save(page_output, format="PNG")
                    safe_print(f"[success]PNG generated: {page_output}[/success]")
            else:
                image = renderer.render_offline(pages[0], context)
                image.save(output, format="PNG")
                safe_print(f"[success]PNG generated: {output}[/success]")
        else:
            image = renderer.render_offline(None, context)
            image.save(output, format="PNG")
            safe_print(f"[success]PNG generated: {output}[/success]")

    table = Table(title="Generation Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Config", config_file)
    table.add_row("Output", output)
    table.add_row("Format", fmt.upper())
    table.add_row("Size", f"{config.width}x{config.height}")

    if config.carousel.enabled:
        all_pages = [p.name for p in config.carousel.pages]
        table.add_row("Carousel pages", ", ".join(all_pages))
        if pages:
            table.add_row("Generated pages", ", ".join(pages))

    if context_vars:
        for key, value in context_vars.items():
            table.add_row(f"Variable: {key}", value)

    console.print(table)
