"""Cache simulation as a time-stepped model.

One step = one key access. Replacement policies: LRU, FIFO, LFU, random.
Access stream: explicit sequence (cycled when exhausted) or generated with
Zipf-distributed key popularity (zipf_exponent 0 = uniform).
"""
from __future__ import annotations

import bisect
from collections import OrderedDict
from typing import Any, ClassVar

from ...core.engine.models_base import TimeSteppedModel
from .params import CacheParams


class CacheModel(TimeSteppedModel):
    model_id: ClassVar[str] = "cache_sim"
    display_name: ClassVar[str] = "Cache Replacement Policies"
    description: ClassVar[str] = (
        "Fixed-capacity cache with LRU/FIFO/LFU/random replacement over an "
        "explicit or Zipf-generated access sequence; reports hit/miss rates "
        "and access cost."
    )
    model_type: ClassVar[str] = "time_stepped"
    version: ClassVar[str] = "1.0.0"
    dt: ClassVar[float] = 1.0
    visualizer: ClassVar[dict[str, Any]] = {
        "kind": "cache",
        "series": ["hit_rate", "hits", "misses"],
    }
    param_model: ClassVar[type] = CacheParams

    def _build_stream(self) -> None:
        """Access stream is fully derived from params; rebuilt on initialize
        and restore (checkpoints carry only _s + rng state)."""
        p = self.params
        if p.accesses is not None:
            self._access_list: list[int] | None = list(p.accesses)
            self._cum = None
        else:
            self._access_list = None
            alpha = p.zipf_exponent
            weights = [1.0 / ((k + 1) ** alpha) for k in range(p.num_keys)]
            total = sum(weights)
            cum = []
            acc = 0.0
            for w in weights:
                acc += w
                cum.append(acc / total)
            self._cum = cum

    def initialize(self, ctx: Any) -> None:
        self._s = {
            "cache": OrderedDict(),  # key -> [freq, insert_seq]
            "accesses_done": 0,
            "hits": 0,
            "misses": 0,
            "total_cost": 0.0,
            "cursor": 0,
            "next_seq": 0,
            "last_key": None,
            "last_hit": None,
            "evicted": None,
        }
        self._build_stream()

    def _next_key(self) -> int:
        if self._access_list is not None:
            key = self._access_list[self._s["cursor"] % len(self._access_list)]
        else:
            r = self.rng.random()
            key = bisect.bisect_left(self._cum, r)
        self._s["cursor"] += 1
        return int(key)

    def _evict(self) -> int:
        cache = self._s["cache"]
        policy = self.params.policy
        if policy in ("lru", "fifo"):
            key, _ = cache.popitem(last=False)
        elif policy == "lfu":
            victim = min(cache, key=lambda k: (cache[k][0], cache[k][1]))
            freq_seq = cache.pop(victim)
            key = victim
        else:  # random
            key = self.rng.choice(list(cache))
            del cache[key]
        return key

    def step(self) -> None:
        st = self._s
        p = self.params
        key = self._next_key()
        st["evicted"] = None
        if key in st["cache"]:
            st["hits"] += 1
            st["last_hit"] = True
            st["total_cost"] += p.cost_hit
            entry = st["cache"][key]
            entry[0] += 1
            if p.policy == "lru":
                st["cache"].move_to_end(key)
        else:
            st["misses"] += 1
            st["last_hit"] = False
            st["total_cost"] += p.cost_miss
            if len(st["cache"]) >= p.capacity:
                st["evicted"] = self._evict()
            st["cache"][key] = [1, st["next_seq"]]
            st["next_seq"] += 1
        st["accesses_done"] += 1
        st["last_key"] = key
        kind = "hit" if st["last_hit"] else "miss"
        self.emit(self._step_time(), kind, f"access key {key} -> {kind}",
                  {"key": key, "size": len(st["cache"]),
                   "evicted": st["evicted"]})

    def _step_time(self) -> float:
        return float(self._s["accesses_done"])

    def dump_state(self) -> dict[str, Any]:
        st = self._s
        return {
            "cache": [[k, v[0], v[1]] for k, v in st["cache"].items()],
            "accesses_done": st["accesses_done"],
            "hits": st["hits"],
            "misses": st["misses"],
            "total_cost": st["total_cost"],
            "cursor": st["cursor"],
            "next_seq": st["next_seq"],
            "last_key": st["last_key"],
            "last_hit": st["last_hit"],
            "evicted": st["evicted"],
        }

    def load_state(self, state: dict[str, Any]) -> None:
        st = dict(state)
        st["cache"] = OrderedDict(
            (k, [freq, seq]) for k, freq, seq in state.get("cache", [])
        )
        self._s = st
        self._build_stream()

    def snapshot(self) -> dict[str, Any]:
        st = self._s
        n = st["accesses_done"]
        return {
            "policy": self.params.policy,
            "capacity": self.params.capacity,
            "size": len(st["cache"]),
            "accesses": n,
            "hits": st["hits"],
            "misses": st["misses"],
            "hit_rate": (st["hits"] / n) if n else 0.0,
            "last_key": st["last_key"],
            "last_hit": st["last_hit"],
            "evicted": st["evicted"],
            "contents": [k for k, _ in st["cache"].items()][:64],
        }

    def finalize_metrics(self) -> dict[str, float]:
        st = self._s
        n = st["accesses_done"]
        return {
            "accesses": float(n),
            "hits": float(st["hits"]),
            "misses": float(st["misses"]),
            "hit_rate": (st["hits"] / n) if n else 0.0,
            "miss_rate": (st["misses"] / n) if n else 0.0,
            "total_cost": st["total_cost"],
            "avg_cost_per_access": (st["total_cost"] / n) if n else 0.0,
        }
