from __future__ import annotations

import io
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from ..config.parser import (
    DashboardConfig,
    DashboardPage,
    build_context,
    evaluate_conditions,
    evaluate_conditions_for_page,
    evaluate_carousel_rules,
    get_page_by_name,
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

TRANSITION_FADE = "fade"
TRANSITION_SLIDE_LEFT = "slide_left"
TRANSITION_SLIDE_RIGHT = "slide_right"
TRANSITION_SLIDE_UP = "slide_up"
TRANSITION_SLIDE_DOWN = "slide_down"


@dataclass
class AlertState:
    active: bool = False
    message: str = ""
    severity: str = "warning"
    start_time: float = 0
    blink_state: bool = False
    last_blink: float = 0


@dataclass
class CarouselState:
    current_page: str = ""
    target_page: str = ""
    is_transitioning: bool = False
    transition_progress: float = 0.0
    transition_start: float = 0.0
    last_page_change: float = 0.0
    last_rule_check: float = 0.0


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
        self._page_widget_states: Dict[str, Dict[int, WidgetRenderState]] = {}
        self._urgent_conditions: List[str] = []

        self.refresh_mode = config.refresh_mode or REFRESH_MODE_AUTO
        self.refresh_interval = config.refresh_interval or DEFAULT_REFRESH_INTERVAL
        self.force_full_refresh_next = False

        self.carousel = CarouselState()
        self.alert = AlertState()

        self._page_images: Dict[str, Image.Image] = {}

        self._init_image()
        self._detect_urgent_conditions()
        self._init_carousel()

    def _init_carousel(self) -> None:
        if self.config.carousel.enabled and self.config.carousel.pages:
            default_page = self.config.carousel.default_page or self.config.carousel.pages[0].name
            self.carousel.current_page = default_page
            self.carousel.target_page = default_page

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
        self._page_widget_states = {}
        self._page_images = {}
        self._init_image()
        self._detect_urgent_conditions()
        self._init_carousel()
        self.force_full_refresh_next = True

    def render_page(self, page_name: str, context: Optional[Dict[str, Any]] = None) -> Image.Image:
        page = get_page_by_name(self.config.carousel, page_name)
        if page is None:
            return self._image.copy() if self._image else self._init_image()

        if context is None:
            metrics = self.fetch_metrics()
            context = build_context(self.config.variables, metrics)

        page_variables = dict(self.config.variables)
        page_variables.update(page.variables)
        page_context = build_context(page_variables, self.current_metrics)

        image = Image.new("RGB", (self.config.width, self.config.height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        page_datasources = list(self.config.datasources) + list(page.datasources)
        active_widgets = evaluate_conditions_for_page(page, page_context)

        for widget_cfg in active_widgets:
            widget = self._create_widget(widget_cfg)
            if widget:
                widget.render(draw, page_context)

        self._page_images[page_name] = image
        return image

    def check_carousel_rules(self, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.config.carousel.enabled:
            return None

        if context is None:
            metrics = self.fetch_metrics()
            context = build_context(self.config.variables, metrics)

        target_page = evaluate_carousel_rules(
            self.config.carousel,
            context,
        )

        if target_page and target_page != self.carousel.current_page:
            return target_page

        return None

    def start_transition(self, target_page: str) -> None:
        if target_page not in [p.name for p in self.config.carousel.pages]:
            return

        self.carousel.target_page = target_page
        self.carousel.is_transitioning = True
        self.carousel.transition_progress = 0.0
        self.carousel.transition_start = time.time()

    def _generate_fade_frames(
        self, from_image: Image.Image, to_image: Image.Image, num_frames: int
    ) -> List[Image.Image]:
        frames = []
        for i in range(1, num_frames + 1):
            alpha = i / num_frames
            frame = Image.blend(from_image, to_image, alpha)
            frames.append(frame)
        return frames

    def _generate_slide_frames(
        self, from_image: Image.Image, to_image: Image.Image, num_frames: int, direction: str
    ) -> List[Image.Image]:
        width, height = self.config.width, self.config.height
        frames = []

        for i in range(1, num_frames + 1):
            progress = i / num_frames
            frame = Image.new("RGB", (width, height), (255, 255, 255))

            if direction == TRANSITION_SLIDE_LEFT:
                offset = int(width * progress)
                frame.paste(from_image, (-offset, 0))
                frame.paste(to_image, (width - offset, 0))
            elif direction == TRANSITION_SLIDE_RIGHT:
                offset = int(width * progress)
                frame.paste(from_image, (offset, 0))
                frame.paste(to_image, (offset - width, 0))
            elif direction == TRANSITION_SLIDE_UP:
                offset = int(height * progress)
                frame.paste(from_image, (0, -offset))
                frame.paste(to_image, (0, height - offset))
            elif direction == TRANSITION_SLIDE_DOWN:
                offset = int(height * progress)
                frame.paste(from_image, (0, offset))
                frame.paste(to_image, (0, offset - height))

            frames.append(frame)

        return frames

    def generate_transition_frames(
        self, from_page: str, to_page: str, num_frames: Optional[int] = None
    ) -> List[Image.Image]:
        if num_frames is None:
            num_frames = self.config.carousel.transition_frames

        from_image = self._page_images.get(from_page) or self.render_page(from_page)
        to_image = self._page_images.get(to_page) or self.render_page(to_page)

        transition = self.config.carousel.transition

        if transition in [TRANSITION_SLIDE_LEFT, TRANSITION_SLIDE_RIGHT, TRANSITION_SLIDE_UP, TRANSITION_SLIDE_DOWN]:
            return self._generate_slide_frames(from_image, to_image, num_frames, transition)
        else:
            return self._generate_fade_frames(from_image, to_image, num_frames)

    def render_with_carousel(self, force_full: bool = False) -> Image.Image:
        if not self.config.carousel.enabled:
            return self.render(force_full=force_full)

        metrics = self.fetch_metrics()
        context = build_context(self.config.variables, metrics)

        now = time.time()
        time_since_check = now - self.carousel.last_rule_check

        if time_since_check >= self.config.carousel.interval and not self.carousel.is_transitioning:
            target_page = self.check_carousel_rules(context)
            if target_page:
                self.start_transition(target_page)
            self.carousel.last_rule_check = now

        if self.carousel.is_transitioning:
            frames = self.generate_transition_frames(
                self.carousel.current_page,
                self.carousel.target_page,
            )
            progress = (now - self.carousel.transition_start) / max(
                self.config.carousel.transition_frames * 0.5, 1.0
            )

            frame_idx = min(int(progress * len(frames)), len(frames) - 1)
            result = frames[frame_idx]

            if progress >= 1.0:
                self.carousel.current_page = self.carousel.target_page
                self.carousel.is_transitioning = False
                self.carousel.last_page_change = now
                self._page_widget_states = {}

            self._draw_alert_border(result)
            self._image = result
            return result

        current_page_image = self.render_page(self.carousel.current_page, context)
        self._draw_alert_border(current_page_image)
        self._image = current_page_image
        return current_page_image

    def _draw_alert_border(self, image: Image.Image) -> None:
        if not self.alert.active:
            return

        now = time.time()
        blink_interval = self.config.webhook.blink_interval

        if now - self.alert.last_blink >= blink_interval:
            self.alert.blink_state = not self.alert.blink_state
            self.alert.last_blink = now

        if not self.alert.blink_state:
            return

        color_map = {
            "critical": (255, 0, 0),
            "warning": (255, 165, 0),
            "info": (0, 0, 255),
        }
        color = color_map.get(self.alert.severity, (255, 0, 0))

        draw = ImageDraw.Draw(image)
        border_width = 6
        for i in range(border_width):
            draw.rectangle(
                [i, i, self.config.width - 1 - i, self.config.height - 1 - i],
                outline=color,
            )

        if self.alert.message:
            draw.rectangle([0, 0, self.config.width, 30], fill=color)
            draw.text((10, 8), self.alert.message[:80], fill=(255, 255, 255))

    def trigger_alert(self, message: str, severity: str = "warning") -> None:
        self.alert.active = True
        self.alert.message = message
        self.alert.severity = severity
        self.alert.start_time = time.time()
        self.alert.blink_state = True
        self.alert.last_blink = time.time()

    def clear_alert(self) -> None:
        self.alert.active = False
        self.alert.message = ""
        self.alert.blink_state = False

    def get_alert_remaining_time(self) -> float:
        if not self.alert.active:
            return 0
        duration = self.config.webhook.blink_duration
        elapsed = time.time() - self.alert.start_time
        return max(0, duration - elapsed)

    def update_alert(self) -> None:
        if self.alert.active and self.get_alert_remaining_time() <= 0:
            self.clear_alert()

    def get_carousel_state(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.carousel.enabled,
            "current_page": self.carousel.current_page,
            "target_page": self.carousel.target_page,
            "is_transitioning": self.carousel.is_transitioning,
            "transition_progress": self.carousel.transition_progress,
            "pages": [p.name for p in self.config.carousel.pages],
            "default_page": self.config.carousel.default_page,
            "transition": self.config.carousel.transition,
            "interval": self.config.carousel.interval,
        }

    def set_carousel_page(self, page_name: str) -> bool:
        if not self.config.carousel.enabled:
            return False

        page = get_page_by_name(self.config.carousel, page_name)
        if page is None:
            return False

        self.start_transition(page_name)
        return True

    def toggle_carousel(self, enabled: Optional[bool] = None) -> bool:
        if enabled is not None:
            self.config.carousel.enabled = enabled
        else:
            self.config.carousel.enabled = not self.config.carousel.enabled

        if self.config.carousel.enabled and not self.carousel.current_page:
            self._init_carousel()

        return self.config.carousel.enabled

    def render_offline(
        self,
        page_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        if context is None:
            context = {}

        if page_name and self.config.carousel.enabled:
            return self.render_page(page_name, context)
        else:
            if self._image is None:
                self._render_full(context)
            return self._image.copy() if self._image else self._init_image()

    def render_to_pdf(
        self,
        output_path: str,
        pages: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        images = []

        if self.config.carousel.enabled:
            page_list = pages or [p.name for p in self.config.carousel.pages]
            for page_name in page_list:
                img = self.render_page(page_name, context)
                images.append(img.convert("RGB"))
        else:
            if self._image is None:
                self._render_full(context or {})
            if self._image:
                images.append(self._image.convert("RGB"))

        if images:
            images[0].save(
                output_path,
                "PDF",
                resolution=100.0,
                save_all=True,
                append_images=images[1:],
            )
