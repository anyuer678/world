from typing import Optional

from pydantic import Field, model_validator

from ...core.engine.models_base import WorldLabParams

_MAX_EDGE_CELLS = 10_000
_MAX_TOTAL_CELLS = 200_000


class NodeSpec(WorldLabParams):
    id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    x: float
    y: float


class EdgeSpec(WorldLabParams):
    src: str = Field(min_length=1, max_length=32)
    dst: str = Field(min_length=1, max_length=32)
    length: Optional[float] = Field(
        default=None, gt=0, description="road length in cells; default = euclidean(src, dst)"
    )


class SignalSpec(WorldLabParams):
    node: str = Field(min_length=1, max_length=32)
    cycle: int = Field(ge=2, le=10_000, description="green A (first half) / green B (second half) alternation period in ticks")
    offset: int = Field(default=0, ge=0, description="phase shift in ticks")
    group_a: list[str] = Field(default_factory=list, description="src node ids allowed to enter during the first half")
    group_b: list[str] = Field(default_factory=list, description="src node ids allowed to enter during the second half")


_DEFAULT_NODES = [
    {"id": "N", "x": 0, "y": -30},
    {"id": "E", "x": 30, "y": 0},
    {"id": "S", "x": 0, "y": 30},
    {"id": "W", "x": -30, "y": 0},
    {"id": "C", "x": 0, "y": 0},
]
_DEFAULT_EDGES = [
    {"src": "N", "dst": "C"},
    {"src": "C", "dst": "S"},
    {"src": "S", "dst": "C"},
    {"src": "C", "dst": "N"},
    {"src": "E", "dst": "C"},
    {"src": "C", "dst": "W"},
    {"src": "W", "dst": "C"},
    {"src": "C", "dst": "E"},
]


class TrafficParams(WorldLabParams):
    nodes: list[NodeSpec] = Field(default_factory=lambda: [NodeSpec(**n) for n in _DEFAULT_NODES], min_length=2)
    edges: list[EdgeSpec] = Field(default_factory=lambda: [EdgeSpec(**e) for e in _DEFAULT_EDGES], min_length=1)
    signals: list[SignalSpec] = Field(default_factory=list)
    v_max: int = Field(default=2, ge=1, le=10, description="max speed in cells per tick")
    slow_prob: float = Field(default=0.15, ge=0, le=1, description="per-vehicle random slowdown probability (0 = deterministic)")
    spawn_rate: float = Field(default=0.4, ge=0, le=1, description="per-source-node spawn probability per tick")
    spawn_nodes: list[str] = Field(default_factory=list, description="spawn sources; empty = all nodes")
    spawn_until: Optional[int] = Field(default=None, ge=0, description="stop spawning after this tick; None = spawn forever")
    max_vehicles: int = Field(default=300, ge=1, le=100_000)

    @model_validator(mode="after")
    def _check_network(self) -> "TrafficParams":
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("node ids must be unique")
        pos = {n.id: (n.x, n.y) for n in self.nodes}
        seen_edges = set()
        total_cells = 0
        for e in self.edges:
            if e.src not in pos:
                raise ValueError(f"edge src {e.src!r} is not a declared node")
            if e.dst not in pos:
                raise ValueError(f"edge dst {e.dst!r} is not a declared node")
            if e.src == e.dst:
                raise ValueError(f"self-loop edge at {e.src!r} is not allowed")
            key = (e.src, e.dst)
            if key in seen_edges:
                raise ValueError(f"duplicate directed edge {e.src}->{e.dst}")
            seen_edges.add(key)
            length = e.length if e.length is not None else ((pos[e.src][0] - pos[e.dst][0]) ** 2 + (pos[e.src][1] - pos[e.dst][1]) ** 2) ** 0.5
            if e.length is None and length < 1e-9:
                raise ValueError(f"edge {e.src}->{e.dst}: coincident nodes need an explicit length")
            cells = max(1, round(length))
            if cells > _MAX_EDGE_CELLS:
                raise ValueError(f"edge {e.src}->{e.dst} length {cells} cells exceeds cap {_MAX_EDGE_CELLS}")
            total_cells += cells
        if total_cells > _MAX_TOTAL_CELLS:
            raise ValueError(f"network total {total_cells} cells exceeds cap {_MAX_TOTAL_CELLS}")
        signal_nodes = set()
        for s in self.signals:
            if s.node not in pos:
                raise ValueError(f"signal node {s.node!r} is not a declared node")
            if s.node in signal_nodes:
                raise ValueError(f"duplicate signal at node {s.node!r}")
            signal_nodes.add(s.node)
            incoming_srcs = {e.src for e in self.edges if e.dst == s.node}
            a, b = set(s.group_a), set(s.group_b)
            if a & b:
                raise ValueError(f"signal at {s.node!r}: group_a and group_b overlap: {sorted(a & b)}")
            covered = a | b
            if covered != incoming_srcs:
                raise ValueError(
                    f"signal at {s.node!r}: group_a/group_b must exactly cover incoming sources "
                    f"{sorted(incoming_srcs)}, got {sorted(covered)}"
                )
        unknown_spawn = [n for n in self.spawn_nodes if n not in pos]
        if unknown_spawn:
            raise ValueError(f"spawn_nodes not declared: {unknown_spawn}")
        return self
