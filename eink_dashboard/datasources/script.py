from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional

from .base import DataPoint, DataSource


class ScriptSource(DataSource):
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.shell = config.get("shell", "/bin/sh")
        self.timeout = config.get("timeout", 30)
        self.workdir = config.get("workdir", None)
        self.env = config.get("env", {})

    def fetch(self, query: str, **kwargs: Any) -> List[DataPoint]:
        script_content = query
        output = self._run_script(script_content)
        return self._parse_output(output)

    def _run_script(self, script_content: str) -> str:
        try:
            if self.shell.endswith("python") or self.shell.endswith("python3"):
                cmd = [self.shell, "-c", script_content]
            else:
                cmd = [self.shell, "-c", script_content]

            env = None
            if self.env:
                import os

                env = os.environ.copy()
                env.update(self.env)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.workdir,
                env=env,
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def _parse_output(self, output: str) -> List[DataPoint]:
        points: List[DataPoint] = []
        now = time.time()

        output = output.strip()
        if not output:
            return points

        try:
            data = json.loads(output)
            return self._parse_json(data, now)
        except (json.JSONDecodeError, ValueError):
            pass

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = re.match(r"^([\w.]+)\s+([\d.eE+-]+)\s*$", line)
            if match:
                name = match.group(1)
                value = float(match.group(2))
                points.append(
                    DataPoint(
                        value=value,
                        timestamp=now,
                        labels={},
                        metric_name=name,
                    )
                )
                continue

            match = re.match(r"^([\d.eE+-]+)\s*$", line)
            if match:
                value = float(match.group(1))
                points.append(
                    DataPoint(
                        value=value,
                        timestamp=now,
                        labels={},
                        metric_name="",
                    )
                )

        return points

    def _parse_json(self, data: Any, now: float) -> List[DataPoint]:
        points: List[DataPoint] = []

        if isinstance(data, dict):
            if "value" in data and isinstance(data["value"], (int, float)):
                points.append(
                    DataPoint(
                        value=float(data["value"]),
                        timestamp=data.get("timestamp", now),
                        labels=data.get("labels", {}),
                        metric_name=data.get("name", ""),
                    )
                )
            else:
                for key, value in data.items():
                    if isinstance(value, (int, float)):
                        points.append(
                            DataPoint(
                                value=float(value),
                                timestamp=now,
                                labels={},
                                metric_name=key,
                            )
                        )
                    elif isinstance(value, dict) and "value" in value:
                        points.append(
                            DataPoint(
                                value=float(value["value"]),
                                timestamp=value.get("timestamp", now),
                                labels=value.get("labels", {}),
                                metric_name=key,
                            )
                        )
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "value" in item:
                    points.append(
                        DataPoint(
                            value=float(item["value"]),
                            timestamp=item.get("timestamp", now),
                            labels=item.get("labels", {}),
                            metric_name=item.get("name", ""),
                        )
                    )
                elif isinstance(item, (int, float)):
                    points.append(
                        DataPoint(
                            value=float(item),
                            timestamp=now,
                            labels={},
                            metric_name="",
                        )
                    )

        return points
