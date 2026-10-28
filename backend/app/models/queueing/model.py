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
    display_name: ClassVar[str] = "排队系统（G/G/c/K）"
    description: ClassVar[str] = (
        "离散事件排队：可配置到达过程（泊松/确定性）、服务时间分布（指数/确定性/均匀）、"
        "服务台数、系统容量与排队规则。适合观察拥堵如何随利用率变化、容量与丢弃的关系。"
    )
    model_type: ClassVar[str] = "discrete_event"
    version: ClassVar[str] = "1.0.0"
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "queue",
        "series": ["queue_length", "busy_servers", "in_system"],
    }
    param_model: ClassVar[type] = QueueingParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "rush-hour",
            "title": "高峰期为什么突然堵死",
            "description": "到达率 0.9、单窗口、平均服务 1.0：利用率 ρ=0.9 贴近极限——队伍越排越长且几乎不再消散。",
            "params": {
                "arrival": {"kind": "poisson", "rate": 0.9},
                "service": {"kind": "exponential", "mean": 1.0},
                "servers": 1,
            },
            "seed": 7,
            "stop_condition": {"type": "steps", "value": 30000},
        },
        {
            "id": "overload-drop",
            "title": "超载的临界点：顾客被丢弃",
            "description": "到达率 1.5 已超过服务能力，且系统容量只有 5：看队伍顶满后，新到的顾客如何被拒之门外。",
            "params": {
                "arrival": {"kind": "poisson", "rate": 1.5},
                "service": {"kind": "exponential", "mean": 1.0},
                "servers": 1,
                "capacity": 5,
            },
            "seed": 11,
            "stop_condition": {"type": "steps", "value": 30000},
        },
        {
            "id": "add-window",
            "title": "多开两个窗口值不值",
            "description": "与「高峰期堵死」同样的到达率 0.9，但开 3 个窗口（ρ=0.3）：对比两者的等待时间，体会利用率对排队的非线性影响。",
            "params": {
                "arrival": {"kind": "poisson", "rate": 0.9},
                "service": {"kind": "exponential", "mean": 1.0},
                "servers": 3,
            },
            "seed": 7,
            "stop_condition": {"type": "steps", "value": 30000},
        },
    ]

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
            "hist": [],
            "hist_stride": 1,
            "hist_n": 0,
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
    def _sample(self, t: float) -> None:
        """Rolling history for the workbench chart: [time, queue_len, busy,
        in_system]. Log decimation keeps ~128-256 samples over any run
        length; lives in _s so checkpoints carry it."""
        st = self._s
        st["hist_n"] += 1
        if st["hist_n"] % st["hist_stride"]:
            return
        st["hist"].append([t, len(st["queue"]), st["busy"], st["in_system"]])
        if len(st["hist"]) > 256:
            st["hist"] = st["hist"][::2]
            st["hist_stride"] *= 2

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
        self._sample(event.time)

    # --- state / snapshot / metrics ----------------------------------------
    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {k: (list(v) if k == "queue" else v) for k, v in st.items()}

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["queue"] = list(state.get("queue", []))
        for k, v in (("hist", []), ("hist_stride", 1), ("hist_n", 0)):
            st.setdefault(k, v)
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
            "sim_time": st["last_t"],
            "history": st["hist"][-256:],
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
