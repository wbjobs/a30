from __future__ import annotations

import base64
import io
import json
import threading
import time
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_file

from ..config.parser import DashboardConfig, load_config
from .renderer import DashboardRenderer


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

    def display(self, image) -> None:
        self.current_image = image
        if self.mock or self._epd is None:
            return
        try:
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
_refresh_thread: Optional[threading.Thread] = None
_running: bool = False
_config: Optional[DashboardConfig] = None
_lock = threading.Lock()


def create_app(mock_display: bool = True) -> Flask:
    global _display
    app = Flask(__name__)

    _display = DisplayDriver(mock=mock_display)
    _display.init()

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "timestamp": time.time()})

    @app.route("/api/config", methods=["PUT", "POST"])
    def update_config():
        global _config, _renderer, _running, _refresh_thread

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        if "yaml" in data:
            import yaml as yaml_mod

            yaml_content = data["yaml"]
            config_data = yaml_mod.safe_load(yaml_content)
            if not config_data:
                return jsonify({"error": "Invalid YAML"}), 400

            from ..config.parser import (
                DashboardConfig,
                DataSourceConfig,
                WidgetConfig,
            )

            name = config_data.get("name", "dashboard")
            width = config_data.get("width", 800)
            height = config_data.get("height", 480)
            refresh_interval = config_data.get("refresh_interval", 30)
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

            config = DashboardConfig(
                name=name,
                width=width,
                height=height,
                refresh_interval=refresh_interval,
                variables=variables,
                datasources=datasources,
                widgets=widgets,
                raw_yaml=yaml_content,
            )
        elif "config" in data:
            config_dict = data["config"]
            from ..config.parser import (
                DashboardConfig,
                DataSourceConfig,
                WidgetConfig,
            )

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

            config = DashboardConfig(
                name=config_dict.get("name", "dashboard"),
                width=config_dict.get("width", 800),
                height=config_dict.get("height", 480),
                refresh_interval=config_dict.get("refresh_interval", 30),
                variables=config_dict.get("variables", {}),
                datasources=datasources,
                widgets=widgets,
                raw_yaml=data.get("yaml", ""),
            )
        else:
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

    @app.route("/api/render", methods=["POST"])
    def render_now():
        global _renderer

        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        with _lock:
            image = _renderer.render()
            if _display:
                _display.display(image)

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
        return jsonify(state)

    @app.route("/api/metrics", methods=["GET"])
    def get_metrics():
        if _renderer is None:
            return jsonify({"error": "No config set"}), 404

        return jsonify({"metrics": _renderer.current_metrics})

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
            interval = _config.refresh_interval
            try:
                with _lock:
                    image = _renderer.render()
                    _display.display(image)
            except Exception:
                pass
            time.sleep(max(1, interval))
        else:
            time.sleep(1)
