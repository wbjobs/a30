from __future__ import annotations

import io
import time
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from ..config.parser import (
    DashboardConfig,
    build_context,
    evaluate_conditions,
    render_template,
)
from ..datasources.base import DataSource
from ..widgets.base import Widget
from ..widgets.line_chart import LineChartWidget
from ..widgets.progress import ProgressWidget
from ..widgets.text import TextWidget


class DashboardRenderer:
    def __init__(self, config: DashboardConfig):
        self.config = config
        self.datasources: Dict[str, DataSource] = {}
        self.current_metrics: Dict[str, Any] = {}
        self.last_render_time: float = 0

    def set_datasource(self, name: str, source: DataSource) -> None:
        self.datasources[name] = source

    def fetch_metrics(self) -> Dict[str, Any]:
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

    def render(self) -> Image.Image:
        metrics = self.fetch_metrics()
        context = build_context(self.config.variables, metrics)

        image = Image.new(
            "RGB",
            (self.config.width, self.config.height),
            (255, 255, 255),
        )
        draw = ImageDraw.Draw(image)

        active_widgets = evaluate_conditions(self.config, context)

        for widget_cfg in active_widgets:
            widget = self._create_widget(widget_cfg)
            if widget:
                widget.render(draw, context)

        self.last_render_time = time.time()
        return image

    def render_to_bytes(self, format: str = "PNG") -> bytes:
        image = self.render()
        buf = io.BytesIO()
        image.save(buf, format=format)
        return buf.getvalue()

    def get_current_state(self) -> Dict[str, Any]:
        return {
            "name": self.config.name,
            "width": self.config.width,
            "height": self.config.height,
            "refresh_interval": self.config.refresh_interval,
            "metrics": self.current_metrics,
            "last_render_time": self.last_render_time,
            "widget_count": len(self.config.widgets),
        }

    def update_config(self, config: DashboardConfig) -> None:
        self.config = config
        self.datasources = {}
