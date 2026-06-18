from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Environment, Undefined


@dataclass
class WidgetConfig:
    type: str
    x: int
    y: int
    width: int
    height: int
    config: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None
    visible: bool = True


@dataclass
class DataSourceConfig:
    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardConfig:
    name: str
    width: int
    height: int
    refresh_interval: int = 60
    refresh_mode: str = "auto"
    variables: Dict[str, Any] = field(default_factory=dict)
    datasources: List[DataSourceConfig] = field(default_factory=list)
    widgets: List[WidgetConfig] = field(default_factory=list)
    raw_yaml: str = ""


def load_config(file_path: str) -> DashboardConfig:
    with open(file_path, "r", encoding="utf-8") as f:
        raw_yaml = f.read()

    data = yaml.safe_load(raw_yaml)
    if not data:
        raise ValueError("Empty or invalid YAML configuration")

    name = data.get("name", "dashboard")
    width = data.get("width", 800)
    height = data.get("height", 480)
    refresh_interval = data.get("refresh_interval", 60)
    refresh_mode = data.get("refresh_mode", "auto")
    variables = data.get("variables", {})

    datasources = []
    for ds in data.get("datasources", []):
        datasources.append(
            DataSourceConfig(
                name=ds["name"],
                type=ds["type"],
                config=ds.get("config", {}),
            )
        )

    widgets = []
    for widget in data.get("widgets", []):
        widgets.append(
            WidgetConfig(
                type=widget["type"],
                x=widget.get("x", 0),
                y=widget.get("y", 0),
                width=widget.get("width", 100),
                height=widget.get("height", 50),
                config=widget.get("config", {}),
                condition=widget.get("condition"),
                visible=True,
            )
        )

    return DashboardConfig(
        name=name,
        width=width,
        height=height,
        refresh_interval=refresh_interval,
        refresh_mode=refresh_mode,
        variables=variables,
        datasources=datasources,
        widgets=widgets,
        raw_yaml=raw_yaml,
    )


def render_template(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            env = Environment(undefined=Undefined)
            template = env.from_string(value)
            try:
                return template.render(**context)
            except Exception:
                return value
        return value
    elif isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [render_template(item, context) for item in value]
    else:
        return value


def evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
    if not condition:
        return True

    env = Environment(undefined=Undefined)
    template = env.from_string(f"{{% if {condition} %}}True{{% else %}}False{{% endif %}}")
    try:
        result = template.render(**context)
        return result == "True"
    except Exception:
        return False


def evaluate_conditions(config: DashboardConfig, context: Dict[str, Any]) -> List[WidgetConfig]:
    active_widgets = []
    for widget in config.widgets:
        visible = True
        if widget.condition:
            visible = evaluate_condition(widget.condition, context)
        widget.visible = visible
        if visible:
            rendered_config = render_template(widget.config, context)
            widget.config = rendered_config
            active_widgets.append(widget)
    return active_widgets


def build_context(variables: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    context = {}
    context.update(variables)
    context.update(metrics)
    return context
