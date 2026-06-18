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
class DashboardPage:
    name: str
    widgets: List[WidgetConfig] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    datasources: List[DataSourceConfig] = field(default_factory=list)


@dataclass
class CarouselRule:
    type: str
    value: str
    target_page: str
    enabled: bool = True


@dataclass
class CarouselConfig:
    enabled: bool = False
    pages: List[DashboardPage] = field(default_factory=list)
    rules: List[CarouselRule] = field(default_factory=list)
    default_page: str = ""
    transition: str = "fade"
    transition_frames: int = 3
    interval: int = 300


@dataclass
class WebhookConfig:
    enabled: bool = False
    endpoint: str = "/api/webhook"
    target_device: str = "all"
    blink_duration: int = 30
    blink_interval: int = 2


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
    carousel: CarouselConfig = field(default_factory=CarouselConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    raw_yaml: str = ""


def _parse_widget(widget_data: Dict[str, Any]) -> WidgetConfig:
    return WidgetConfig(
        type=widget_data["type"],
        x=widget_data.get("x", 0),
        y=widget_data.get("y", 0),
        width=widget_data.get("width", 100),
        height=widget_data.get("height", 50),
        config=widget_data.get("config", {}),
        condition=widget_data.get("condition"),
        visible=True,
    )


def _parse_datasource(ds_data: Dict[str, Any]) -> DataSourceConfig:
    return DataSourceConfig(
        name=ds_data["name"],
        type=ds_data["type"],
        config=ds_data.get("config", {}),
    )


def _parse_page(page_data: Dict[str, Any]) -> DashboardPage:
    widgets = [_parse_widget(w) for w in page_data.get("widgets", [])]
    datasources = [_parse_datasource(ds) for ds in page_data.get("datasources", [])]
    return DashboardPage(
        name=page_data["name"],
        widgets=widgets,
        variables=page_data.get("variables", {}),
        datasources=datasources,
    )


def _parse_carousel(carousel_data: Optional[Dict[str, Any]]) -> CarouselConfig:
    if not carousel_data:
        return CarouselConfig()

    pages = [_parse_page(p) for p in carousel_data.get("pages", [])]
    rules = []
    for rule_data in carousel_data.get("rules", []):
        rules.append(
            CarouselRule(
                type=rule_data["type"],
                value=rule_data["value"],
                target_page=rule_data["target_page"],
                enabled=rule_data.get("enabled", True),
            )
        )

    return CarouselConfig(
        enabled=carousel_data.get("enabled", False),
        pages=pages,
        rules=rules,
        default_page=carousel_data.get("default_page", pages[0].name if pages else ""),
        transition=carousel_data.get("transition", "fade"),
        transition_frames=carousel_data.get("transition_frames", 3),
        interval=carousel_data.get("interval", 300),
    )


def _parse_webhook(webhook_data: Optional[Dict[str, Any]]) -> WebhookConfig:
    if not webhook_data:
        return WebhookConfig()

    return WebhookConfig(
        enabled=webhook_data.get("enabled", False),
        endpoint=webhook_data.get("endpoint", "/api/webhook"),
        target_device=webhook_data.get("target_device", "all"),
        blink_duration=webhook_data.get("blink_duration", 30),
        blink_interval=webhook_data.get("blink_interval", 2),
    )


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

    datasources = [_parse_datasource(ds) for ds in data.get("datasources", [])]
    widgets = [_parse_widget(w) for w in data.get("widgets", [])]
    carousel = _parse_carousel(data.get("carousel"))
    webhook = _parse_webhook(data.get("webhook"))

    return DashboardConfig(
        name=name,
        width=width,
        height=height,
        refresh_interval=refresh_interval,
        refresh_mode=refresh_mode,
        variables=variables,
        datasources=datasources,
        widgets=widgets,
        carousel=carousel,
        webhook=webhook,
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


def evaluate_conditions_for_page(page: DashboardPage, context: Dict[str, Any]) -> List[WidgetConfig]:
    active_widgets = []
    for widget in page.widgets:
        visible = True
        if widget.condition:
            visible = evaluate_condition(widget.condition, context)
        widget.visible = visible
        if visible:
            rendered_config = render_template(widget.config, context)
            widget.config = rendered_config
            active_widgets.append(widget)
    return active_widgets


def evaluate_carousel_rules(
    config: CarouselConfig,
    context: Dict[str, Any],
    current_time: Optional[float] = None,
) -> Optional[str]:
    import datetime

    if current_time is None:
        current_time = datetime.datetime.now()
    else:
        current_time = datetime.datetime.fromtimestamp(current_time)

    weekday = current_time.weekday()
    is_weekday = weekday < 5
    hour = current_time.hour
    minute = current_time.minute

    for rule in config.rules:
        if not rule.enabled:
            continue

        if rule.type == "time_range":
            try:
                start_str, end_str = rule.value.split("-")
                start_h, start_m = map(int, start_str.split(":"))
                end_h, end_m = map(int, end_str.split(":"))

                current_total = hour * 60 + minute
                start_total = start_h * 60 + start_m
                end_total = end_h * 60 + end_m

                if start_total <= current_total < end_total:
                    return rule.target_page
            except Exception:
                continue

        elif rule.type == "weekday":
            try:
                if rule.value == "workday" and is_weekday:
                    return rule.target_page
                elif rule.value == "weekend" and not is_weekday:
                    return rule.target_page
            except Exception:
                continue

        elif rule.type == "condition":
            try:
                if evaluate_condition(rule.value, context):
                    return rule.target_page
            except Exception:
                continue

        elif rule.type == "interval":
            return rule.target_page

    return None


def get_page_by_name(config: CarouselConfig, page_name: str) -> Optional[DashboardPage]:
    for page in config.pages:
        if page.name == page_name:
            return page
    return None
