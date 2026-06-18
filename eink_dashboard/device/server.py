from __future__ import annotations

import io
import json
import os
import threading
import time
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_file, make_response

from ..config.parser import (
    DashboardConfig,
    DataSourceConfig,
    WidgetConfig,
    CarouselConfig,
    WebhookConfig,
    _parse_carousel,
    _parse_webhook,
    build_context,
    load_config,
)
from .renderer import (
    REFRESH_MODE_AUTO,
    REFRESH_MODE_FULL,
    REFRESH_MODE_PARTIAL,
    DashboardRenderer,
)


class BatteryMonitor:
    def __init__(self, mock: bool = True):
        self.mock = mock
        self._battery_level: Optional[float] = 100.0
        self._charging: bool = False

    def get_level(self) -> Optional[float]:
        if self.mock:
            return self._battery_level

        try:
            if os.path.exists("/sys/class/power_supply/BAT0/capacity"):
                with open("/sys/class/power_supply/BAT0/capacity", "r") as f:
                    return float(f.read().strip())
            elif os.path.exists("/proc/apm"):
                with open("/proc/apm", "r") as f:
                    parts = f.read().split()
                    if len(parts) >= 8:
                        return float(parts[7])
        except Exception:
            pass
        return None

    def is_charging(self) -> bool:
        if self.mock:
            return self._charging

        try:
            if os.path.exists("/sys/class/power_supply/BAT0/status"):
                with open("/sys/class/power_supply/BAT0/status", "r") as f:
                    status = f.read().strip().lower()
                    return "charging" in status or "full" in status
        except Exception:
            pass
        return False


class DisplayDriver:
    def __init__(self, mock: bool = True):
        self.mock = mock
        self.current_image = None
        self._epd = None

    def init(self) -> None:
        if self.mock:
            return
        try:
            from waveshare_epd import epd7in5_V2

            self._epd = epd7in5_V2.EPD()
            self._epd.init()
        except ImportError:
            self.mock = True

    def display(self, image, partial: bool = False) -> None:
        self.current_image = image
        if self.mock or self._epd is None:
            return
        try:
            if partial and hasattr(self._epd, "displayPartial"):
                self._epd.displayPartial(self._epd.getbuffer(image))
            else:
                self._epd.display(self._epd.getbuffer(image))
        except Exception:
            pass

    def display_region(self, image, x: int, y: int, w: int, h: int) -> None:
        self.current_image = image
        if self.mock or self._epd is None:
            return
        try:
            if hasattr(self._epd, "displayPartial"):
                region = image.crop((x, y, x + w, y + h))
                buf = self._epd.getbuffer(region)
                self._epd.displayPartial(buf)
            else:
                self._epd.display(self._epd.getbuffer(image))
        except Exception:
            pass

    def clear(self) -> None:
        if self.mock or self._epd is None:
            return
        try:
            self._epd.Clear()
        except Exception:
            pass

    def sleep(self) -> None:
        if self.mock or self._epd is None:
            return
        try:
            self._epd.sleep()
        except Exception:
            pass


_renderer: Optional[DashboardRenderer] = None
_display: Optional[DisplayDriver] = None
_battery: Optional[BatteryMonitor] = None
_refresh_thread: Optional[threading.Thread] = None
_running: bool = False
_config: Optional[DashboardConfig] = None
_lock = threading.Lock()


def _parse_config_from_request(data: Dict[str, Any]) -> Optional[DashboardConfig]:
    if "yaml" in data:
        import yaml as yaml_mod

        yaml_content = data["yaml"]
        config_data = yaml_mod.safe_load(yaml_content)
        if not config_data:
            return None

        name = config_data.get("name", "dashboard")
        width = config_data.get("width", 800)
        height = config_data.get("height", 480)
        refresh_interval = config_data.get("refresh_interval", 60)
        refresh_mode = config_data.get("refresh_mode", "auto")
        variables = config_data.get("variables", {})

        datasources = []
        for ds in config_data.get("datasources", []):
            datasources.append(
                DataSourceConfig(
                    name=ds["name"],
                    type=ds["type"],
                    config=ds.get("config", {}),
                )
            )

        widgets = []
        for w in config_data.get("widgets", []):
            widgets.append(
                WidgetConfig(
                    type=w["type"],
                    x=w.get("x", 0),
                    y=w.get("y", 0),
                    width=w.get("width", 100),
                    height=w.get("height", 50),
                    config=w.get("config", {}),
                    condition=w.get("condition"),
                    visible=True,
                )
            )

        carousel = _parse_carousel(config_data.get("carousel"))
        webhook = _parse_webhook(config_data.get("webhook"))

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
            raw_yaml=yaml_content,
        )
    elif "config" in data:
        config_dict = data["config"]
        datasources = []
        for ds in config_dict.get("datasources", []):
            datasources.append(
                DataSourceConfig(
                    name=ds["name"],
                    type=ds["type"],
                    config=ds.get("config", {}),
                )
            )

        widgets = []
        for w in config_dict.get("widgets", []):
            widgets.append(
                WidgetConfig(
                    type=w["type"],
                    x=w.get("x", 0),
                    y=w.get("y", 0),
                    width=w.get("width", 100),
                    height=w.get("height", 50),
                    config=w.get("config", {}),
                    condition=w.get("condition"),
                    visible=True,
                )
            )

        carousel = _parse_carousel(config_dict.get("carousel"))
        webhook = _parse_webhook(config_dict.get("webhook"))

        return DashboardConfig(
            name=config_dict.get("name", "dashboard"),
            width=config_dict.get("width", 800),
            height=config_dict.get("height", 480),
            refresh_interval=config_dict.get("refresh_interval", 60),
            refresh_mode=config_dict.get("refresh_mode", "auto"),
            variables=config_dict.get("variables", {}),
            datasources=datasources,
            widgets=widgets,
            carousel=carousel,
            webhook=webhook,
            raw_yaml=data.get("yaml", ""),
        )
    return None


def create_app(mock_display: bool = True, mock_battery: bool = True) -> Flask:
    global _display, _battery
    app = Flask(__name__)

    _display = DisplayDriver(mock=mock_display)
    _display.init()

    _battery = BatteryMonitor(mock=mock_battery)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "timestamp": time.time()})

    @app.route("/api/battery", methods=["GET"])
    def battery():
        if _battery is None:
            return jsonify({"error": "Battery monitor not available"}), 503

        level = _battery.get_level()
        charging = _battery.is_charging()

        return jsonify({
            "level": level,
            "charging": charging,
            "timestamp": time.time(),
        })

    @app.route("/api/config", methods=["PUT", "POST"])
    def update_config():
        global _config, _renderer, _running, _refresh_thread

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        config = _parse_config_from_request(data)
        if config is None:
            return jsonify({"error": "Missing 'yaml' or 'config' in request"}), 400

        with _lock:
            _config = config
            _renderer = DashboardRenderer(config)

        if not _running:
            _start_refresh_thread()

        return jsonify({"status": "ok", "message": "Config updated"})

    @app.route("/api/config", methods=["GET"])
    def get_config():
        if _config is None:
            return jsonify({"error": "No config set"}), 404
        return jsonify(
            {
                "name": _config.name,
                "width": _config.width,
                "height": _config.height,
                "refresh_interval": _config.refresh_interval,
                "yaml": _config.raw_yaml,
            }
        )

    @app.route("/api/refresh-mode", methods=["GET"])
    def get_refresh_mode():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404
        return jsonify({
            "mode": _renderer.refresh_mode,
            "interval": _renderer.refresh_interval,
            "effective_interval": _renderer.get_effective_refresh_interval(
                build_context(_config.variables, _renderer.current_metrics) if _config else {}
            ),
            "available_modes": [REFRESH_MODE_FULL, REFRESH_MODE_PARTIAL, REFRESH_MODE_AUTO],
        })

    @app.route("/api/refresh-mode", methods=["PUT", "POST"])
    def set_refresh_mode():
        global _renderer

        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json() or {}
        mode = data.get("mode")
        interval = data.get("interval")

        if mode:
            try:
                _renderer.set_refresh_mode(mode)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

        if interval is not None:
            try:
                _renderer.refresh_interval = max(5, int(interval))
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid interval"}), 400

        return jsonify({
            "status": "ok",
            "mode": _renderer.refresh_mode,
            "interval": _renderer.refresh_interval,
        })

    @app.route("/api/render", methods=["POST"])
    def render_now():
        global _renderer

        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json(silent=True) or {}
        force_full = data.get("force_full", False)

        with _lock:
            image = _renderer.render(force_full=force_full)
            changed_regions = _renderer.get_changed_regions()
            if _display:
                _display.display(image, partial=not force_full)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        response = make_response(send_file(buf, mimetype="image/png"))
        response.headers["X-Changed-Regions"] = json.dumps(changed_regions)
        response.headers["X-Refresh-Type"] = "full" if force_full else "partial"
        return response

    @app.route("/api/render-full", methods=["POST"])
    def render_full():
        global _renderer

        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        with _lock:
            image = _renderer.render(force_full=True)
            if _display:
                _display.display(image, partial=False)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        return send_file(buf, mimetype="image/png")

    @app.route("/api/image", methods=["GET"])
    def get_image():
        if _display and _display.current_image:
            buf = io.BytesIO()
            _display.current_image.save(buf, format="PNG")
            buf.seek(0)
            return send_file(buf, mimetype="image/png")
        return jsonify({"error": "No image available"}), 404

    @app.route("/api/state", methods=["GET"])
    def get_state():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        state = _renderer.get_current_state()

        if _battery:
            state["battery"] = {
                "level": _battery.get_level(),
                "charging": _battery.is_charging(),
            }

        return jsonify(state)

    @app.route("/api/metrics", methods=["GET"])
    def get_metrics():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        return jsonify({"metrics": _renderer.current_metrics})

    @app.route("/api/carousel", methods=["GET"])
    def get_carousel():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        return jsonify(_renderer.get_carousel_state())

    @app.route("/api/carousel", methods=["PUT"])
    def set_carousel():
        global _renderer
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json(silent=True) or {}
        action = data.get("action")
        page = data.get("page")
        enabled = data.get("enabled")

        if action == "toggle":
            result = _renderer.toggle_carousel(enabled)
            return jsonify({"enabled": result})
        elif action == "set_page" and page:
            success = _renderer.set_carousel_page(page)
            if success:
                return jsonify({"status": "ok", "page": page})
            return jsonify({"error": "Invalid page"}), 400
        elif action == "next":
            pages = _renderer.get_carousel_state()["pages"]
            current = _renderer.carousel.current_page
            if pages and current in pages:
                idx = pages.index(current)
                next_idx = (idx + 1) % len(pages)
                _renderer.set_carousel_page(pages[next_idx])
                return jsonify({"status": "ok", "page": pages[next_idx]})
        elif action == "prev":
            pages = _renderer.get_carousel_state()["pages"]
            current = _renderer.carousel.current_page
            if pages and current in pages:
                idx = pages.index(current)
                prev_idx = (idx - 1) % len(pages)
                _renderer.set_carousel_page(pages[prev_idx])
                return jsonify({"status": "ok", "page": pages[prev_idx]})

        return jsonify({"error": "Invalid action"}), 400

    @app.route("/api/carousel/transition", methods=["POST"])
    def get_transition_frames():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json(silent=True) or {}
        from_page = data.get("from_page")
        to_page = data.get("to_page")
        num_frames = data.get("num_frames")

        if not from_page or not to_page:
            return jsonify({"error": "from_page and to_page required"}), 400

        try:
            frames = _renderer.generate_transition_frames(from_page, to_page, num_frames)
            buf = io.BytesIO()
            frames[0].save(
                buf,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=200,
                loop=0,
            )
            buf.seek(0)
            return send_file(buf, mimetype="image/gif")
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/alert", methods=["GET"])
    def get_alert():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        return jsonify({
            "active": _renderer.alert.active,
            "message": _renderer.alert.message,
            "severity": _renderer.alert.severity,
            "remaining_time": _renderer.get_alert_remaining_time(),
        })

    @app.route("/api/alert", methods=["POST"])
    def trigger_alert():
        global _renderer
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json(silent=True) or {}
        message = data.get("message", "Alert")
        severity = data.get("severity", "warning")

        _renderer.trigger_alert(message, severity)
        return jsonify({"status": "ok", "message": message, "severity": severity})

    @app.route("/api/alert", methods=["DELETE"])
    def clear_alert():
        global _renderer
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        _renderer.clear_alert()
        return jsonify({"status": "ok"})

    @app.route("/api/webhook/prometheus", methods=["POST"])
    def prometheus_webhook():
        global _renderer, _config

        data = request.get_json(silent=True) or {}

        alerts = data.get("alerts", [])
        if not alerts:
            return jsonify({"status": "no alerts"})

        firing_alerts = [a for a in alerts if a.get("status") == "firing"]
        if not firing_alerts:
            if _renderer:
                _renderer.clear_alert()
            return jsonify({"status": "resolved"})

        alert = firing_alerts[0]
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        alert_name = labels.get("alertname", "Alert")
        severity = labels.get("severity", "warning")
        message = annotations.get("summary", annotations.get("description", alert_name))

        if _renderer:
            _renderer.trigger_alert(message, severity)

        if _config and _config.webhook.target_device and _config.webhook.target_device != "local":
            try:
                from ..config.device_manager import DeviceManager
                dm = DeviceManager()
                results = dm.broadcast_refresh(_config.webhook.target_device)
                return jsonify({
                    "status": "alert_triggered",
                    "message": message,
                    "severity": severity,
                    "broadcast_results": results,
                })
            except Exception:
                pass

        return jsonify({
            "status": "alert_triggered",
            "message": message,
            "severity": severity,
        })

    @app.route("/api/render-page", methods=["POST"])
    def render_page():
        global _renderer
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        data = request.get_json(silent=True) or {}
        page_name = data.get("page")
        display = data.get("display", True)

        if not page_name:
            return jsonify({"error": "page required"}), 400

        with _lock:
            image = _renderer.render_page(page_name)
            if display and _display:
                _display.display(image, partial=False)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    return app


def _start_refresh_thread() -> None:
    global _running, _refresh_thread

    if _running:
        return

    _running = True
    _refresh_thread = threading.Thread(target=_refresh_loop, daemon=True)
    _refresh_thread.start()


def _refresh_loop() -> None:
    global _renderer, _display, _config

    while _running:
        if _renderer and _config and _display:
            try:
                _renderer.update_alert()
                needs_update = _renderer.alert.active

                context = build_context(_config.variables, _renderer.current_metrics)
                interval = _renderer.get_effective_refresh_interval(context)

                with _lock:
                    if _config.carousel.enabled:
                        image = _renderer.render_with_carousel()
                        changed_regions = _renderer.get_changed_regions()
                    else:
                        image = _renderer.render()
                        changed_regions = _renderer.get_changed_regions()

                    if changed_regions or _renderer.last_full_refresh == _renderer.last_render_time or needs_update:
                        _display.display(image, partial=len(changed_regions) > 0 and not needs_update)

            except Exception:
                pass

            time.sleep(max(1, interval))
        else:
            time.sleep(1)
