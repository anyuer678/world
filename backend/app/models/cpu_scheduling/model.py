"""CPU scheduling as a discrete-event model.

Events: job arrival, completion (non-preemptive) or quantum expiry (rr).
Strategies: FCFS, SJF (non-preemptive), priority (non-preemptive, smaller
value = higher), Round Robin. Outputs waiting/turnaround/response times and
CPU utilization. Workload: explicit job list or generated random workload.
"""
from __future__ import annotations

from typing import Any, ClassVar

from ...core.engine.models_base import DiscreteEventModel
from ...core.engine.event_queue import SimEvent
from .params import CpuSchedulingParams

_EPS = 1e-9

_SELECT_KEY = {
    "fcfs": lambda j: (j["arrival"], j["seq"]),
    "sjf": lambda j: (j["service"], j["arrival"], j["seq"]),
    "priority": lambda j: (j["priority"], j["arrival"], j["seq"]),
    "rr": lambda j: j["enq"],
}


class CpuSchedulingModel(DiscreteEventModel):
    model_id: ClassVar[str] = "cpu_scheduling"
    display_name: ClassVar[str] = "CPU 调度"
    description: ClassVar[str] = (
        "单 CPU 上调度一批作业：先来先服务（FCFS）、短作业优先（SJF）、优先级、"
        "时间片轮转（RR）。输出平均等待/周转/响应时间与 CPU 利用率，"
        "适合观察调度策略与时间片长短对排队时间的影响。"
    )
    model_type: ClassVar[str] = "discrete_event"
    version: ClassVar[str] = "1.0.0"
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "cpu_schedule",
        "series": ["ready_count", "completed", "cpu_utilization"],
    }
    param_model: ClassVar[type] = CpuSchedulingParams
    scenarios: ClassVar[list[dict[str, Any]]] = [
        {
            "id": "rr-quantum-too-small",
            "title": "时间片切得太碎会怎样",
            "description": (
                "Round Robin 的时间片设为 0.1，作业几乎刚开跑就被打断，"
                "来回切换把周转时间拉得很长——时间片不是越小越公平。"
            ),
            "params": {"strategy": "rr", "quantum": 0.1, "num_jobs": 30},
            "seed": 5,
            "stop_condition": {"type": "steps", "value": 20000},
        },
        {
            "id": "rr-quantum-larger",
            "title": "把时间片放大 5 倍",
            "description": (
                "同样的作业（同随机种子），时间片改为 0.5：切换少了，"
                "周转时间明显缩短。对比上一个场景，找到合适的时间片。"
            ),
            "params": {"strategy": "rr", "quantum": 0.5, "num_jobs": 30},
            "seed": 5,
            "stop_condition": {"type": "steps", "value": 20000},
        },
        {
            "id": "sjf-vs-others",
            "title": "短作业优先为什么省时间",
            "description": (
                "同样的作业换成 SJF 策略：让短作业先跑完，平均等待时间通常最低——"
                "代价是长作业可能一直被插队（饥饿）。"
            ),
            "params": {"strategy": "sjf", "num_jobs": 30},
            "seed": 5,
            "stop_condition": {"type": "steps", "value": 20000},
        },
    ]

    def initialize(self, ctx: Any) -> None:
        self._s = self._fresh_state()
        p = self.params
        if p.jobs is not None:
            ordered = sorted(
                enumerate(p.jobs), key=lambda t: (t[1].arrival, t[0])
            )
            pending = [
                {
                    "seq": i,
                    "arrival": float(job.arrival),
                    "service": float(job.service),
                    "priority": int(job.priority),
                    "remaining": float(job.service),
                    "first_dispatch": None,
                    "enq": 0,
                }
                for i, (_, job) in enumerate(ordered)
            ]
        else:
            pending = []
            t = 0.0
            for i in range(p.num_jobs):
                t += self.rng.expovariate(p.arrival_rate)
                svc = self.rng.uniform(p.service_min, p.service_max)
                prio = self.rng.randint(p.priority_low, p.priority_high)
                pending.append(
                    {
                        "seq": i,
                        "arrival": t,
                        "service": svc,
                        "priority": prio,
                        "remaining": svc,
                        "first_dispatch": None,
                        "enq": 0,
                    }
                )
        self._s["pending"] = pending
        if pending:
            first = pending[0]
            ctx.schedule(first["arrival"], "arrival", {"seq": first["seq"]})

    @staticmethod
    def _fresh_state() -> dict[str, Any]:
        return {
            "pending": [],
            "ready": [],
            "running": None,
            "running_since": 0.0,
            "next_enq": 1,
            "arrived": 0,
            "completed": 0,
            "started": 0,
            "total_wait": 0.0,
            "total_turnaround": 0.0,
            "total_response": 0.0,
            "busy_time": 0.0,
            "last_t": 0.0,
        }

    # --- helpers ----------------------------------------------------------
    def _integrate(self, now: float) -> None:
        st = self._s
        if now > st["last_t"]:
            if st["running"] is not None:
                st["busy_time"] += now - st["last_t"]
            st["last_t"] = now

    def _dispatch(self, ctx: Any) -> None:
        st = self._s
        if st["running"] is not None or not st["ready"]:
            return
        key = _SELECT_KEY[self.params.strategy]
        idx = min(range(len(st["ready"])), key=lambda i: key(st["ready"][i]))
        job = st["ready"].pop(idx)
        st["running"] = job
        st["running_since"] = ctx.now
        if job["first_dispatch"] is None:
            job["first_dispatch"] = ctx.now
            st["started"] += 1
            st["total_response"] += ctx.now - job["arrival"]
        if self.params.strategy == "rr":
            ctx.schedule(min(self.params.quantum, job["remaining"]), "quantum", {"job": job})
        else:
            ctx.schedule(job["service"], "completion", {"job": job})
        self.emit(ctx.now, "dispatch", f"job #{job['seq']} dispatched", {"seq": job["seq"]})

    def _finish(self, job: dict[str, Any], now: float) -> None:
        st = self._s
        st["running"] = None
        st["completed"] += 1
        turnaround = now - job["arrival"]
        st["total_turnaround"] += turnaround
        st["total_wait"] += turnaround - job["service"]
        job["remaining"] = 0.0
        self.emit(now, "job_complete", f"job #{job['seq']} completed",
                  {"seq": job["seq"], "turnaround": turnaround})

    # --- event handlers ---------------------------------------------------
    def handle_event(self, event: SimEvent, ctx: Any) -> None:
        st = self._s
        self._integrate(event.time)
        if event.kind == "arrival":
            st["arrived"] += 1
            job = st["pending"].pop(0)
            job["enq"] = st["next_enq"]
            st["next_enq"] += 1
            st["ready"].append(job)
            pending = st["pending"]
            if pending:
                nxt = pending[0]
                ctx.schedule(nxt["arrival"] - event.time, "arrival", {"seq": nxt["seq"]})
            self.emit(event.time, "arrival", f"job #{job['seq']} arrived",
                      {"seq": job["seq"], "service": job["service"]})
            if st["running"] is None:
                self._dispatch(ctx)
        elif event.kind == "completion":
            self._finish(event.payload["job"], event.time)
            self._dispatch(ctx)
        elif event.kind == "quantum":
            job = event.payload["job"]
            served = event.time - st["running_since"]
            job["remaining"] = max(job["remaining"] - served, 0.0)
            if job["remaining"] <= _EPS:
                self._finish(job, event.time)
            else:
                st["running"] = None
                job["enq"] = st["next_enq"]
                st["next_enq"] += 1
                st["ready"].append(job)
                self.emit(event.time, "preempt", f"job #{job['seq']} preempted",
                          {"seq": job["seq"], "remaining": job["remaining"]})
            self._dispatch(ctx)
        else:  # pragma: no cover
            raise ValueError(f"unknown event kind {event.kind!r}")

    # --- state / snapshot / metrics ----------------------------------------
    def dump_state(self) -> dict[str, Any]:
        return {
            k: (list(v) if k in ("pending", "ready") else v)
            for k, v in self._s.items()
        }

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["pending"] = list(state.get("pending", []))
        st["ready"] = list(state.get("ready", []))
        st["running"] = dict(state["running"]) if state.get("running") else None
        self._s = st

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        running = st["running"]
        return {
            "strategy": self.params.strategy,
            "quantum": self.params.quantum if self.params.strategy == "rr" else None,
            "arrived": st["arrived"],
            "completed": st["completed"],
            "pending_count": len(st["pending"]),
            "ready_count": len(st["ready"]),
            "running": (
                {"seq": running["seq"], "remaining": round(running["remaining"], 6)}
                if running
                else None
            ),
            "ready": [
                {
                    "seq": j["seq"],
                    "service": round(j["service"], 6),
                    "remaining": round(j["remaining"], 6),
                    "priority": j["priority"],
                }
                for j in st["ready"][:50]
            ],
            "cpu_utilization": (st["busy_time"] / st["last_t"]) if st["last_t"] > 0 else 0.0,
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        t_end = st["last_t"]
        return {
            "arrived": float(st["arrived"]),
            "completed": float(st["completed"]),
            "avg_waiting_time": (st["total_wait"] / st["completed"]) if st["completed"] else 0.0,
            "avg_turnaround_time": (st["total_turnaround"] / st["completed"]) if st["completed"] else 0.0,
            "avg_response_time": (st["total_response"] / st["started"]) if st["started"] else 0.0,
            "cpu_utilization": (st["busy_time"] / t_end) if t_end > 0 else 0.0,
            "throughput": (st["completed"] / t_end) if t_end > 0 else 0.0,
            "sim_time_end": t_end,
        }
