from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DataPoint:
    value: float
    timestamp: float
    labels: Dict[str, str]
    metric_name: str = ""


class DataSource(ABC):
    name: str

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def fetch(self, query: str, **kwargs: Any) -> List[DataPoint]:
        pass

    def fetch_single(self, query: str, **kwargs: Any) -> Optional[float]:
        points = self.fetch(query, **kwargs)
        if points:
            return points[0].value
        return None
