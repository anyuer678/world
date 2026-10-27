"""Queueing system G/G/c/K as a discrete-event model.

Events: arrival, departure. Ordering handled by the engine's event queue.
Supports Poisson/deterministic arrivals, exponential/deterministic/uniform
service, multiple servers, finite system capacity (blocking/dropping), and
FIFO/LCFS (non-preemptive) queue disciplines.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import DiscreteEventModel
from ...core.engine.event_queue import SimEvent
from .params import QueueingParams


class QueueingModel(DiscreteEventModel):
    model_id: ClassVar[str] = "queueing"
    display_name: ClassVar[str] = "Queueing System (G/G/c/K)"
    description: ClassVar[str] = (
        "Discrete-event queue with configurable arrival process, service time "
        "distribution, number of servers, system capacity and queue discipline."
    )
    model_type: ClassVar[str] = "discrete_event"
    version: ClassVar[str] = "1.0.0"
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "queue",
        "series": ["queue_length", "busy_servers", "in_system"],
    }
    param_model: ClassVar[type] = QueueingParams

    def initialize(self, ctx: Any) -> None:
        self._s = self._fresh_counters()
        ctx.schedule(self._interarrival(), "arrival")

    @staticmethod
    def _fresh_counters() -> dict[str, Any]:
        return {
            "next_seq": 0,
            "arrived": 0,
            "dropped_measured": 0,
            "served_total": 0,
            "served_measured": 0,
            "started_service": 0,
            "in_system": 0,
            "busy": 0,
            "queue": [],
            "total_wait": 0.0,
            "total_response": 0.0,
            "busy_time": 0.0,
            "queue_area": 0.0,
            "last_t": 0.0,
            "metrics_on": False,
        }

    # --- stochastic draws -------------------------------------------------
    def _interarrival(self) -> float:
        a = self.params.arrival
        if a.kind == "deterministic":
            return 1.0 / a.rate
        return self.rng.expovariate(a.rate)

    def _service_time(self) -> float:
        s = self.params.service
        if s.kind == "deterministic":
            return s.mean
        if s.kind == "uniform":
            return self.rng.uniform(s.mean - s.half_spread, s.mean + s.half_spread)
        return self.rng.expovariate(1.0 / s.mean)

    # --- helpers ----------------------------------------------------------
    def _integrate(self, now: float) -> None:
        st = self._s
        dt = now - st["last_t"]
        if dt > 0:
            st["busy_time"] += st["busy"] * dt
            st["queue_area"] += len(st["queue"]) * dt
            st["last_t"] = now

    def _start_service(self, cust: dict[str, Any], ctx: Any) -> None:
        st = self._s
        st["busy"] += 1
        if st["metrics_on"]:
            st["total_wait"] += ctx.now - cust["arrival_time"]
            st["started_service"] += 1
        self.emit(ctx.now, "service_start", f"customer #{cust['seq']} enters service",
                  {"seq": cust["seq"], "wait": ctx.now - cust["arrival_time"]})
        ctx.schedule(cust["service"], "departure", {"customer": cust})

    # --- event handlers ---------------------------------------------------
    def handle_event(self, event: SimEvent, ctx: Any) -> None:
        st = self._s
        self._integrate(event.time)
        if event.kind == "arrival":
            st["arrived"] += 1
            if st["arrived"] > self.params.warmup_customers and not st["metrics_on"]:
                st["metrics_on"] = True
            cap = self.params.capacity
            if cap is not None and st["in_system"] >= cap:
                if st["metrics_on"]:
                    st["dropped_measured"] += 1
                self.emit(event.time, "drop", "customer dropped (system full)",
                          {"in_system": st["in_system"]})
            else:
                st["in_system"] += 1
                cust = {
                    "seq": st["next_seq"],
                    "arrival_time": event.time,
                    "service": self._service_time(),
                }
                st["next_seq"] += 1
                if st["busy"] < self.params.servers:
                    self._start_service(cust, ctx)
                else:
                    st["queue"].append(cust)
            ctx.schedule(self._interarrival(), "arrival")
        elif event.kind == "departure":
            cust = event.payload["customer"]
            st["busy"] -= 1
            st["in_system"] -= 1
            st["served_total"] += 1
            if st["metrics_on"]:
                st["served_measured"] += 1
                st["total_response"] += event.time - cust["arrival_time"]
            self.emit(event.time, "departure", f"customer #{cust['seq']} departs",
                      {"seq": cust["seq"], "response": event.time - cust["arrival_time"]})
            if st["queue"]:
                nxt = st["queue"].pop() if self.params.discipline == "lcfs" else st["queue"].pop(0)
                self._start_service(nxt, ctx)
        else:  # pragma: no cover
            raise ValueError(f"unknown event kind {event.kind!r}")

    # --- state / snapshot / metrics ----------------------------------------
    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {k: (list(v) if k == "queue" else v) for k, v in st.items()}

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["queue"] = list(state.get("queue", []))
        self._s = st

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        return {
            "servers": self.params.servers,
            "capacity": self.params.capacity,
            "discipline": self.params.discipline,
            "queue_length": len(st["queue"]),
            "busy_servers": st["busy"],
            "in_system": st["in_system"],
            "arrived": st["arrived"],
            "dropped": st["dropped_measured"],
            "served": st["served_total"],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        t_end = st["last_t"]
        servers = self.params.servers
        measured_arrivals = max(st["arrived"] - self.params.warmup_customers, 0)
        return {
            "arrived": float(st["arrived"]),
            "dropped": float(st["dropped_measured"]),
            "served": float(st["served_total"]),
            "drop_rate": (st["dropped_measured"] / measured_arrivals) if measured_arrivals else 0.0,
            "throughput": (st["served_total"] / t_end) if t_end > 0 else 0.0,
            "avg_waiting_time": (st["total_wait"] / st["started_service"]) if st["started_service"] else 0.0,
            "avg_response_time": (st["total_response"] / st["served_measured"]) if st["served_measured"] else 0.0,
            "utilization": (st["busy_time"] / (t_end * servers)) if t_end > 0 and servers else 0.0,
            "avg_queue_length": (st["queue_area"] / t_end) if t_end > 0 else 0.0,
            "final_queue_length": float(len(st["queue"])),
            "sim_time_end": t_end,
        }
