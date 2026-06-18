from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from PIL import ImageDraw, ImageFont


class Widget(ABC):
    def __init__(self, x: int, y: int, width: int, height: int, config: Dict[str, Any]):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.config = config

    @abstractmethod
    def render(self, draw: ImageDraw.ImageDraw, context: Dict[str, Any]) -> None:
        pass

    def get_font(self, size: int = 16) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except (OSError, IOError):
            try:
                return ImageFont.truetype("Arial.ttf", size)
            except (OSError, IOError):
                return ImageFont.load_default()

    def parse_color(self, color: str, default: Tuple[int, int, int] = (0, 0, 0)) -> Tuple[int, int, int]:
        if color.startswith("#"):
            color = color[1:]
            if len(color) == 6:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                return (r, g, b)
        color_map = {
            "black": (0, 0, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "gray": (128, 128, 128),
            "yellow": (255, 255, 0),
        }
        return color_map.get(color.lower(), default)
