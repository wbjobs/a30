from __future__ import annotations

import io
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from ..config.parser import (
    DashboardConfig,
    build_context,
    evaluate_conditions,
    render_template,
    evaluate_condition,
)
from ..datasources.base import DataSource
from ..widgets.base import Widget
from ..widgets.line_chart import LineChartWidget
from ..widgets.progress import ProgressWidget
from ..widgets.text import TextWidget


REFRESH_MODE_FULL = "full"
REFRESH_MODE_PARTIAL = "partial"
REFRESH_MODE_AUTO = "auto"

DEFAULT_REFRESH_INTERVAL = 60
URGENT_REFRESH_INTERVAL = 5


@dataclass
class WidgetRenderState:
    widget_type: str
    x: int
    y: int
    width: int
    height: int
    config_hash: str
    visible: bool
    last_render_data: str = ""
    urgent: bool = False


class DashboardRenderer:
    def __init__(self, config: DashboardConfig):
        self.config = config
        self.datasources: Dict[str, DataSource] = {}
        self.current_metrics: Dict[str, Any] = {}
        self.last_metrics: Dict[str, Any] = {}
        self.last_render_time: float = 0
        self.last_full_refresh: float = 0

        self._image: Optional[Image.Image] = None
        self._widget_states: Dict[int, WidgetRenderState] = {}
        self._urgent_conditions: List[str] = []

        self.refresh_mode = config.refresh_mode or REFRESH_MODE_AUTO
        self.refresh_interval = config.refresh_interval or DEFAULT_REFRESH_INTERVAL
        self.force_full_refresh_next = False

        self._init_image()
        self._detect_urgent_conditions()

    def _init_image(self) -> None:
        self._image = Image.new(
            "RGB",
            (self.config.width, self.config.height),
            (255, 255, 255),
        )

    def _detect_urgent_conditions(self) -> None:
        self._urgent_conditions = []
        for widget in self.config.widgets:
            if widget.condition:
                cond_lower = widget.condition.lower()
                if any(kw in cond_lower for kw in ["warning", "alert", "urgent", "> 70", ">70", "warn", "alarm"]):
                    self._urgent_conditions.append(widget.condition)

    def _compute_config_hash(self, config: Dict[str, Any]) -> str:
        serialized = str(sorted(config.items()))
        return hashlib.md5(serialized.encode()).hexdigest()

    def set_datasource(self, name: str, source: DataSource) -> None:
        self.datasources[name] = source

    def fetch_metrics(self) -> Dict[str, Any]:
        self.last_metrics = dict(self.current_metrics)
        metrics: Dict[str, Any] = {}

        for ds_config in self.config.datasources:
            ds_name = ds_config.name
            ds_type = ds_config.type
            ds_conf = ds_config.config

            if ds_name not in self.datasources:
                if ds_type == "prometheus":
                    from ..datasources.prometheus import PrometheusSource

                    self.datasources[ds_name] = PrometheusSource(ds_name, ds_conf)
                elif ds_type == "script":
                    from ..datasources.script import ScriptSource

                    self.datasources[ds_name] = ScriptSource(ds_name, ds_conf)

            source = self.datasources.get(ds_name)
            if source is None:
                continue

            queries = ds_conf.get("queries", {})
            if not queries:
                continue

            for metric_key, query in queries.items():
                value = source.fetch_single(query)
                if value is not None:
                    metrics[metric_key] = value

        self.current_metrics = metrics
        return metrics

    def _has_metric_changes(self) -> bool:
        if set(self.current_metrics.keys()) != set(self.last_metrics.keys()):
            return True
        for key, value in self.current_metrics.items():
            old_value = self.last_metrics.get(key)
            if old_value is None:
                return True
            if isinstance(value, float) and isinstance(old_value, float):
                if abs(value - old_value) > 0.01:
                    return True
            elif value != old_value:
                return True
        return False

    def _check_urgent_condition(self, context: Dict[str, Any]) -> bool:
        for condition in self._urgent_conditions:
            if evaluate_condition(condition, context):
                return True
        return False

    def get_effective_refresh_interval(self, context: Dict[str, Any]) -> int:
        if self._check_urgent_condition(context):
            return URGENT_REFRESH_INTERVAL
        return self.refresh_interval

    def _create_widget(self, widget_config: Any) -> Optional[Widget]:
        widget_type = widget_config.type
        x = widget_config.x
        y = widget_config.y
        width = widget_config.width
        height = widget_config.height
        config = widget_config.config

        if widget_type == "text":
            return TextWidget(x, y, width, height, config)
        elif widget_type == "line_chart":
            return LineChartWidget(x, y, width, height, config)
        elif widget_type == "progress":
            return ProgressWidget(x, y, width, height, config)
        else:
            return None

    def _get_widget_render_signature(self, widget: Widget, context: Dict[str, Any]) -> str:
        config = widget.config
        rendered = render_template(config, context)
        return str(sorted(rendered.items()))

    def _clear_region(self, x: int, y: int, w: int, h: int) -> None:
        if self._image is None:
            return
        draw = ImageDraw.Draw(self._image)
        draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255))

    def render(self, force_full: bool = False) -> Image.Image:
        metrics = self.fetch_metrics()
        context = build_context(self.config.variables, metrics)

        should_full_refresh = (
            force_full
            or self.force_full_refresh_next
            or self._image is None
            or self.refresh_mode == REFRESH_MODE_FULL
        )

        if self.refresh_mode == REFRESH_MODE_AUTO:
            time_since_full = time.time() - self.last_full_refresh
            if time_since_full > 600:
                should_full_refresh = True

        if should_full_refresh:
            return self._render_full(context)

        has_changes = self._has_metric_changes()
        if not has_changes:
            self.last_render_time = time.time()
            return self._image.copy() if self._image else self._render_full(context)

        return self._render_partial(context)

    def _render_full(self, context: Dict[str, Any]) -> Image.Image:
        if self._image is None or self._image.size != (self.config.width, self.config.height):
            self._init_image()
        else:
            draw = ImageDraw.Draw(self._image)
            draw.rectangle(
                [0, 0, self.config.width, self.config.height],
                fill=(255, 255, 255),
            )

        draw = ImageDraw.Draw(self._image)
        active_widgets = evaluate_conditions(self.config, context)

        self._widget_states = {}
        for idx, widget_cfg in enumerate(active_widgets):
            widget = self._create_widget(widget_cfg)
            if widget:
                widget.render(draw, context)
                config_hash = self._compute_config_hash(widget.config)
                self._widget_states[idx] = WidgetRenderState(
                    widget_type=widget_cfg.type,
                    x=widget_cfg.x,
                    y=widget_cfg.y,
                    width=widget_cfg.width,
                    height=widget_cfg.height,
                    config_hash=config_hash,
                    visible=widget_cfg.visible,
                    last_render_data=self._get_widget_render_signature(widget, context),
                )

        self.last_full_refresh = time.time()
        self.last_render_time = time.time()
        self.force_full_refresh_next = False

        return self._image.copy()

    def _render_partial(self, context: Dict[str, Any]) -> Image.Image:
        if self._image is None:
            return self._render_full(context)

        draw = ImageDraw.Draw(self._image)
        active_widgets = evaluate_conditions(self.config, context)

        changed_regions: List[Tuple[int, int, int, int]] = []

        for idx, widget_cfg in enumerate(active_widgets):
            old_state = self._widget_states.get(idx)
            widget = self._create_widget(widget_cfg)
            if not widget:
                continue

            config_hash = self._compute_config_hash(widget.config)
            current_render_data = self._get_widget_render_signature(widget, context)

            changed = False
            if old_state is None:
                changed = True
            elif old_state.visible != widget_cfg.visible:
                changed = True
            elif old_state.config_hash != config_hash:
                changed = True
            elif old_state.last_render_data != current_render_data:
                changed = True

            if changed:
                self._clear_region(
                    widget_cfg.x, widget_cfg.y,
                    widget_cfg.width, widget_cfg.height
                )
                widget.render(draw, context)

                self._widget_states[idx] = WidgetRenderState(
                    widget_type=widget_cfg.type,
                    x=widget_cfg.x,
                    y=widget_cfg.y,
                    width=widget_cfg.width,
                    height=widget_cfg.height,
                    config_hash=config_hash,
                    visible=widget_cfg.visible,
                    last_render_data=current_render_data,
                )

                changed_regions.append(
                    (widget_cfg.x, widget_cfg.y,
                     widget_cfg.x + widget_cfg.width,
                     widget_cfg.y + widget_cfg.height)
                )

        for idx in list(self._widget_states.keys()):
            if idx >= len(active_widgets):
                state = self._widget_states.pop(idx)
                self._clear_region(state.x, state.y, state.width, state.height)
                changed_regions.append((state.x, state.y, state.x + state.width, state.y + state.height))

        self.last_render_time = time.time()
        self._changed_regions = changed_regions

        return self._image.copy()

    def get_changed_regions(self) -> List[Tuple[int, int, int, int]]:
        return getattr(self, "_changed_regions", [])

    def render_to_bytes(self, format: str = "PNG", force_full: bool = False) -> bytes:
        image = self.render(force_full=force_full)
        buf = io.BytesIO()
        image.save(buf, format=format)
        return buf.getvalue()

    def get_current_state(self) -> Dict[str, Any]:
        return {
            "name": self.config.name,
            "width": self.config.width,
            "height": self.config.height,
            "refresh_interval": self.get_effective_refresh_interval(
                build_context(self.config.variables, self.current_metrics)
            ),
            "refresh_mode": self.refresh_mode,
            "metrics": self.current_metrics,
            "last_render_time": self.last_render_time,
            "last_full_refresh": self.last_full_refresh,
            "widget_count": len(self.config.widgets),
            "has_urgent": self._check_urgent_condition(
                build_context(self.config.variables, self.current_metrics)
            ),
        }

    def set_refresh_mode(self, mode: str) -> None:
        if mode not in [REFRESH_MODE_FULL, REFRESH_MODE_PARTIAL, REFRESH_MODE_AUTO]:
            raise ValueError(f"Invalid refresh mode: {mode}")
        self.refresh_mode = mode

    def schedule_full_refresh(self) -> None:
        self.force_full_refresh_next = True

    def update_config(self, config: DashboardConfig) -> None:
        self.config = config
        self.datasources = {}
        self._widget_states = {}
        self._init_image()
        self._detect_urgent_conditions()
        self.force_full_refresh_next = True
