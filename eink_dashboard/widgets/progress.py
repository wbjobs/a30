from __future__ import annotations

from typing import Any, Dict

from PIL import ImageDraw

from .base import Widget


class ProgressWidget(Widget):
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def render(self, draw: ImageDraw.ImageDraw, context: Dict[str, Any]) -> None:
        value = self._safe_float(self.config.get("value", 0), 0.0)
        max_value = self._safe_float(self.config.get("max", 100), 100.0)
        min_value = self._safe_float(self.config.get("min", 0), 0.0)
        label = self.config.get("label", "")
        show_percent = self.config.get("show_percent", True)
        color_str = self.config.get("color", "black")
        bar_color_str = self.config.get("bar_color", "black")
        direction = self.config.get("direction", "horizontal")

        color = self.parse_color(color_str)
        bar_color = self.parse_color(bar_color_str)
        bg_color = (240, 240, 240)

        percentage = (value - min_value) / (max_value - min_value)
        percentage = max(0, min(1, percentage))

        bar_height_ratio = 0.6
        bar_w = int(self.width * 0.7)
        bar_h = int(self.height * bar_height_ratio)

        bar_x = self.x
        bar_y = self.y + (self.height - bar_h) // 2

        if label:
            label_font = self.get_font(12)
            draw.text((self.x, self.y), label, fill=color, font=label_font)

        draw.rectangle(
            [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
            fill=bg_color,
            outline=color,
        )

        fill_w = int(bar_w * percentage)
        if fill_w > 0:
            draw.rectangle(
                [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
                fill=bar_color,
            )

        if show_percent:
            percent_text = f"{int(percentage * 100)}%"
            font = self.get_font(12)

            try:
                bbox = draw.textbbox((0, 0), percent_text, font=font)
                text_w = bbox[2] - bbox[0]
            except AttributeError:
                text_w, _ = draw.textsize(percent_text, font=font)

            text_x = bar_x + bar_w + 8
            text_y = bar_y + (bar_h - 12) // 2
            draw.text((text_x, text_y), percent_text, fill=color, font=font)
