"""In-memory evaluation store (the MVP deliberately has no database)."""

from __future__ import annotations

import threading
from collections import OrderedDict

from app.models import EvaluationResult

MAX_STORED = 100


class EvaluationStore:
    def __init__(self, capacity: int = MAX_STORED) -> None:
        self._items: OrderedDict[str, EvaluationResult] = OrderedDict()
        self._capacity = capacity
        self._lock = threading.Lock()

    def save(self, result: EvaluationResult) -> None:
        with self._lock:
            self._items[result.evaluation_id] = result
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get(self, evaluation_id: str) -> EvaluationResult | None:
        with self._lock:
            return self._items.get(evaluation_id)
