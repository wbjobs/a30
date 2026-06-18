from __future__ import annotations

from typing import Any, Dict, List

from PIL import ImageDraw

from .base import Widget


class LineChartWidget(Widget):
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def render(self, draw: ImageDraw.ImageDraw, context: Dict[str, Any]) -> None:
        data = self.config.get("data", [])
        title = self.config.get("title", "")
        color_str = self.config.get("color", "black")
        show_grid = self.config.get("show_grid", True)
        y_min = self.config.get("y_min")
        y_max = self.config.get("y_max")

        color = self.parse_color(color_str)
        gray = (200, 200, 200)

        padding_top = 20 if title else 5
        padding_bottom = 5
        padding_left = 5
        padding_right = 5

        chart_x = self.x + padding_left
        chart_y = self.y + padding_top
        chart_width = self.width - padding_left - padding_right
        chart_height = self.height - padding_top - padding_bottom

        if title:
            title_font = self.get_font(12)
            draw.text((chart_x, self.y + 2), title, fill=color, font=title_font)

        if not data:
            draw.rectangle(
                [chart_x, chart_y, chart_x + chart_width, chart_y + chart_height],
                outline=gray,
            )
            return

        values: List[float] = []
        for item in data:
            if isinstance(item, (int, float)):
                values.append(float(item))
            elif isinstance(item, str):
                val = self._safe_float(item)
                if val is not None:
                    values.append(val)
            elif isinstance(item, dict) and "value" in item:
                val = self._safe_float(item["value"])
                if val is not None:
                    values.append(val)

        if not values:
            return

        actual_min = min(values) if y_min is None else self._safe_float(y_min, min(values))
        actual_max = max(values) if y_max is None else self._safe_float(y_max, max(values))

        if actual_min == actual_max:
            actual_max = actual_min + 1

        if show_grid:
            for i in range(5):
                y = chart_y + (chart_height * i) // 4
                draw.line(
                    [(chart_x, y), (chart_x + chart_width, y)],
                    fill=gray,
                    width=1,
                )

        n = len(values)
        if n < 2:
            x_pos = chart_x + chart_width // 2
            y_pos = chart_y + chart_height - int(
                (values[0] - actual_min) / (actual_max - actual_min) * chart_height
            )
            draw.ellipse([x_pos - 2, y_pos - 2, x_pos + 2, y_pos + 2], fill=color)
            return

        points = []
        for i, value in enumerate(values):
            x = chart_x + int((i / (n - 1)) * chart_width)
            y = chart_y + chart_height - int(
                (value - actual_min) / (actual_max - actual_min) * chart_height
            )
            y = max(chart_y, min(chart_y + chart_height, y))
            points.append((x, y))

        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=color, width=2)

        if self.config.get("show_points", False):
            for px, py in points:
                draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=color)

        draw.rectangle(
            [chart_x, chart_y, chart_x + chart_width, chart_y + chart_height],
            outline=color,
            width=1,
        )
