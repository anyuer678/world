"""ModelSpec version evolution: upgrade chain from older schema versions."""
from __future__ import annotations

from typing import Any, Callable

from .errors import SpecValidationError

SPEC_CURRENT_VERSION = 1

_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_migration(from_version: int, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    _MIGRATIONS[from_version] = fn


def _v0_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    """v0 (prototype): {model, params, horizon} -> v1."""
    if "model" not in raw:
        raise SpecValidationError.single("migration_error", "v0 spec requires 'model'")
    upgraded = {
        "schema_version": 1,
        "model_id": raw["model"],
        "params": raw.get("params", {}),
    }
    if "horizon" in raw:
        upgraded["stop_condition"] = {"type": "steps", "value": int(raw["horizon"])}
    if "seed" in raw:
        upgraded["seed"] = raw["seed"]
    return upgraded


register_migration(0, _v0_to_v1)


def upgrade_spec(raw: dict[str, Any]) -> dict[str, Any]:
    version = raw.get("schema_version")
    if version is None:
        # Legacy v0 payloads carry "model"; modern specs may omit schema_version.
        version = 0 if "model" in raw else SPEC_CURRENT_VERSION
    if not isinstance(version, int):
        raise SpecValidationError.single("schema_version", "must be an integer")
    if version > SPEC_CURRENT_VERSION:
        raise SpecValidationError.single(
            "schema_too_new",
            f"spec schema_version {version} newer than supported {SPEC_CURRENT_VERSION}",
        )
    while version < SPEC_CURRENT_VERSION:
        fn = _MIGRATIONS.get(version)
        if fn is None:
            raise SpecValidationError.single(
                "migration_missing", f"no migration from schema_version {version}"
            )
        raw = fn(raw)
        version = raw.get("schema_version", version + 1)
    return raw
