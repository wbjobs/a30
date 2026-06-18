from __future__ import annotations

from typing import Any, Dict

from PIL import ImageDraw

from .base import Widget


class TextWidget(Widget):
    def render(self, draw: ImageDraw.ImageDraw, context: Dict[str, Any]) -> None:
        text = str(self.config.get("text", ""))
        font_size = int(self.config.get("font_size", 16))
        color_str = self.config.get("color", "black")
        align = self.config.get("align", "left")
        valign = self.config.get("valign", "top")

        color = self.parse_color(color_str)
        font = self.get_font(font_size)

        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = draw.textsize(text, font=font)

        if align == "center":
            draw_x = self.x + (self.width - text_width) // 2
        elif align == "right":
            draw_x = self.x + self.width - text_width
        else:
            draw_x = self.x

        if valign == "middle":
            draw_y = self.y + (self.height - text_height) // 2
        elif valign == "bottom":
            draw_y = self.y + self.height - text_height
        else:
            draw_y = self.y

        draw.text((draw_x, draw_y), text, fill=color, font=font)
