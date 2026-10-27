from __future__ import annotations

import heapq
from typing import Any

from .base import ENGINE_VERSION, SimulationError


class SimEvent:
    __slots__ = ("time", "priority", "seq", "kind", "payload")

    def __init__(self, time: float, priority: int, seq: int, kind: str, payload: dict[str, Any]):
        self.time = time
        self.priority = priority
        self.seq = seq
        self.kind = kind
        self.payload = payload

    def __repr__(self) -> str:  # pragma: no cover
        return f"SimEvent(t={self.time}, prio={self.priority}, seq={self.seq}, kind={self.kind})"

    def to_json(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "priority": self.priority,
            "seq": self.seq,
            "kind": self.kind,
            "payload": self.payload,
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> "SimEvent":
        return SimEvent(float(d["time"]), int(d["priority"]), int(d["seq"]), str(d["kind"]), dict(d["payload"]))


class EventQueue:
    """Priority queue ordered by (time, priority, seq).

    `seq` is a monotonic insertion counter: identical (time, priority) events
    come out FIFO, which makes same-timestamp and zero-delay ordering
    deterministic and reproducible for a given seed.
    """

    __slots__ = ("_heap", "_seq")

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, int, str, dict[str, Any]]] = []
        self._seq = 0

    def push(self, time: float, kind: str, payload: dict[str, Any] | None = None, priority: int = 0) -> int:
        if time < 0:
            raise SimulationError(f"event time must be >= 0, got {time}")
        self._seq += 1
        heapq.heappush(self._heap, (float(time), int(priority), self._seq, kind, payload or {}))
        return self._seq

    def pop(self) -> SimEvent | None:
        if not self._heap:
            return None
        time, priority, seq, kind, payload = heapq.heappop(self._heap)
        return SimEvent(time, priority, seq, kind, payload)

    def peek(self) -> SimEvent | None:
        if not self._heap:
            return None
        time, priority, seq, kind, payload = self._heap[0]
        return SimEvent(time, priority, seq, kind, payload)

    def __len__(self) -> int:
        return len(self._heap)

    def to_json(self) -> list[dict[str, Any]]:
        return [SimEvent(*item).to_json() for item in self._heap]

    def load_json(self, items: list[dict[str, Any]]) -> None:
        self._heap = [
            (float(d["time"]), int(d["priority"]), int(d["seq"]), str(d["kind"]), dict(d["payload"]))
            for d in items
        ]
        heapq.heapify(self._heap)
        self._seq = max((int(d["seq"]) for d in items), default=0)
