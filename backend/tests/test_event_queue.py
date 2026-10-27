import pytest

from app.core.engine.event_queue import EventQueue
from app.core.engine.base import SimulationError


def test_order_by_time():
    q = EventQueue()
    q.push(5.0, "a")
    q.push(1.0, "b")
    q.push(3.0, "c")
    assert [e.kind for e in iter(lambda: q.pop(), None)] == ["b", "c", "a"]


def test_priority_breaks_time_ties():
    q = EventQueue()
    q.push(1.0, "low", priority=5)
    q.push(1.0, "high", priority=1)
    q.push(1.0, "mid", priority=3)
    assert [e.kind for e in iter(lambda: q.pop(), None)] == ["high", "mid", "low"]


def test_same_time_same_priority_fifo():
    q = EventQueue()
    for i in range(5):
        q.push(2.0, f"e{i}")
    assert [e.kind for e in iter(lambda: q.pop(), None)] == [f"e{i}" for i in range(5)]


def test_zero_delay_keeps_insertion_order():
    q = EventQueue()
    q.push(0.5, "x")
    q.push(1.0, "a")
    q.push(1.0, "b")
    assert [e.kind for e in iter(lambda: q.pop(), None)] == ["x", "a", "b"]


def test_negative_time_rejected():
    q = EventQueue()
    with pytest.raises(SimulationError):
        q.push(-1.0, "x")


def test_json_roundtrip_preserves_order():
    q = EventQueue()
    q.push(1.0, "a", {"k": 1}, priority=2)
    q.push(1.0, "b", {"k": 2}, priority=2)
    q.push(0.5, "c")
    data = q.to_json()
    q2 = EventQueue()
    q2.load_json(data)
    assert [e.kind for e in iter(lambda: q2.pop(), None)] == ["c", "a", "b"]
