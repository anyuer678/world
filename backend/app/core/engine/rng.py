"""RNG helpers: JSON-roundtrippable state for checkpoints."""
from __future__ import annotations

import random
from typing import Any


def make_rng(seed: int | None) -> random.Random:
    return random.Random(seed)


def rng_state_to_json(rng: random.Random) -> dict[str, Any]:
    version, internal, gauss_next = rng.getstate()
    return {"version": version, "internal": list(internal), "gauss_next": gauss_next}


def rng_state_from_json(rng: random.Random, data: dict[str, Any]) -> None:
    internal = tuple(int(x) for x in data["internal"])
    gauss_next = data["gauss_next"]
    if isinstance(gauss_next, list):
        gauss_next = tuple(gauss_next)
    rng.setstate((int(data["version"]), internal, gauss_next))
