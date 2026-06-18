from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from .base import DataPoint, DataSource


class PrometheusSource(DataSource):
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self.base_url = config.get("base_url", "http://localhost:9090")
        self.timeout = config.get("timeout", 10)

    def fetch(self, query: str, **kwargs: Any) -> List[DataPoint]:
        endpoint = f"{self.base_url}/api/v1/query"
        params = {"query": query}
        if "time" in kwargs:
            params["time"] = kwargs["time"]

        try:
            response = requests.get(endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                return []

            result = data.get("data", {}).get("result", [])
            points: List[DataPoint] = []

            for item in result:
                metric = item.get("metric", {})
                value_data = item.get("value", [])
                if value_data:
                    timestamp = float(value_data[0])
                    value = float(value_data[1])
                    points.append(
                        DataPoint(
                            value=value,
                            timestamp=timestamp,
                            labels={k: v for k, v in metric.items() if k != "__name__"},
                            metric_name=metric.get("__name__", ""),
                        )
                    )

            return points
        except requests.RequestException:
            return []

    def fetch_range(self, query: str, start: float, end: float, step: str = "1m") -> List[DataPoint]:
        endpoint = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        try:
            response = requests.get(endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                return []

            result = data.get("data", {}).get("result", [])
            points: List[DataPoint] = []

            for item in result:
                metric = item.get("metric", {})
                values = item.get("values", [])
                for ts_val in values:
                    timestamp = float(ts_val[0])
                    value = float(ts_val[1])
                    points.append(
                        DataPoint(
                            value=value,
                            timestamp=timestamp,
                            labels={k: v for k, v in metric.items() if k != "__name__"},
                            metric_name=metric.get("__name__", ""),
                        )
                    )

            return points
        except requests.RequestException:
            return []
