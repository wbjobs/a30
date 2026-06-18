from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import requests
import yaml

from eink_dashboard.utils.console import safe_print


@dataclass
class DeviceInfo:
    name: str
    url: str
    groups: List[str] = field(default_factory=lambda: ["all"])
    description: str = ""
    timeout: int = 10

    # Runtime state
    online: bool = False
    battery_level: Optional[float] = None
    last_check: float = 0
    last_metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class DeviceManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._default_config_path()
        self.devices: Dict[str, DeviceInfo] = {}
        self._load_config()

    def _default_config_path(self) -> str:
        home = os.path.expanduser("~")
        return os.path.join(home, ".eink", "devices.yaml")

    def _load_config(self) -> None:
        if not os.path.exists(self.config_path):
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for dev_data in data.get("devices", []):
                device = DeviceInfo(
                    name=dev_data["name"],
                    url=dev_data["url"],
                    groups=dev_data.get("groups", ["all"]),
                    description=dev_data.get("description", ""),
                    timeout=dev_data.get("timeout", 10),
                )
                self.devices[device.name] = device
        except Exception as e:
            safe_print(f"[warning]Warning: Could not load device config: {e}[/warning]")

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        data = {
            "devices": [
                {
                    "name": d.name,
                    "url": d.url,
                    "groups": d.groups,
                    "description": d.description,
                    "timeout": d.timeout,
                }
                for d in self.devices.values()
            ]
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def add_device(self, name: str, url: str, groups: Optional[List[str]] = None,
                   description: str = "") -> DeviceInfo:
        if name in self.devices:
            raise ValueError(f"Device '{name}' already exists")

        device = DeviceInfo(
            name=name,
            url=url.rstrip("/"),
            groups=groups or ["all"],
            description=description,
        )
        self.devices[name] = device
        self.save()
        return device

    def remove_device(self, name: str) -> None:
        if name not in self.devices:
            raise ValueError(f"Device '{name}' not found")
        del self.devices[name]
        self.save()

    def get_device(self, name: str) -> Optional[DeviceInfo]:
        return self.devices.get(name)

    def get_devices_by_group(self, group: str) -> List[DeviceInfo]:
        if group == "all":
            return list(self.devices.values())
        return [d for d in self.devices.values() if group in d.groups]

    def list_groups(self) -> List[str]:
        groups = set()
        for d in self.devices.values():
            groups.update(d.groups)
        return sorted(groups)

    def check_status(self, device: DeviceInfo) -> bool:
        try:
            resp = requests.get(f"{device.url}/api/health", timeout=device.timeout)
            device.online = resp.ok
            device.error = None if resp.ok else f"HTTP {resp.status_code}"

            if device.online:
                try:
                    batt_resp = requests.get(f"{device.url}/api/battery", timeout=device.timeout)
                    if batt_resp.ok:
                        batt_data = batt_resp.json()
                        device.battery_level = batt_data.get("level")
                except requests.RequestException:
                    pass

                try:
                    metrics_resp = requests.get(f"{device.url}/api/metrics", timeout=device.timeout)
                    if metrics_resp.ok:
                        device.last_metrics = metrics_resp.json().get("metrics", {})
                except requests.RequestException:
                    pass

            device.last_check = time.time()
            return device.online
        except requests.RequestException as e:
            device.online = False
            device.error = str(e)
            device.last_check = time.time()
            return False

    def check_all(self) -> List[DeviceInfo]:
        for device in self.devices.values():
            self.check_status(device)
        return list(self.devices.values())

    def broadcast_push(self, group: str, yaml_content: str) -> Dict[str, Any]:
        devices = self.get_devices_by_group(group)
        results = {
            "total": len(devices),
            "success": 0,
            "failed": 0,
            "devices": {},
        }

        for device in devices:
            try:
                resp = requests.put(
                    f"{device.url}/api/config",
                    json={"yaml": yaml_content},
                    timeout=device.timeout,
                )
                if resp.ok:
                    results["success"] += 1
                    results["devices"][device.name] = {
                        "status": "success",
                        "message": resp.json().get("message", "Updated"),
                    }
                else:
                    results["failed"] += 1
                    results["devices"][device.name] = {
                        "status": "failed",
                        "error": f"HTTP {resp.status_code}: {resp.text}",
                    }
            except requests.RequestException as e:
                results["failed"] += 1
                results["devices"][device.name] = {
                    "status": "failed",
                    "error": str(e),
                }

        return results

    def broadcast_refresh(self, group: str, full_refresh: bool = False) -> Dict[str, Any]:
        devices = self.get_devices_by_group(group)
        results = {
            "total": len(devices),
            "success": 0,
            "failed": 0,
            "devices": {},
        }

        endpoint = "/api/render-full" if full_refresh else "/api/render"

        for device in devices:
            try:
                resp = requests.post(f"{device.url}{endpoint}", timeout=device.timeout)
                if resp.ok:
                    results["success"] += 1
                    results["devices"][device.name] = {"status": "success"}
                else:
                    results["failed"] += 1
                    results["devices"][device.name] = {
                        "status": "failed",
                        "error": f"HTTP {resp.status_code}",
                    }
            except requests.RequestException as e:
                results["failed"] += 1
                results["devices"][device.name] = {
                    "status": "failed",
                    "error": str(e),
                }

        return results
