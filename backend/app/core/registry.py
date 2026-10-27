"""Plugin registry. Models register themselves; core code never imports a
model package directly. Adding a model = new package + one import in
app/models/__init__.py."""
from __future__ import annotations

from typing import Any, Optional, Type

from .engine.base import ModelType
from .engine.models_base import BaseWorldModel, DiscreteEventModel, TimeSteppedModel


class RegistryError(Exception):
    pass


class ModelRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, Type[BaseWorldModel]]] = {}

    def register(self, cls: Type[BaseWorldModel]) -> Type[BaseWorldModel]:
        missing = [
            name
            for name in ("model_id", "display_name", "model_type", "param_model", "version")
            if not getattr(cls, name, None)
        ]
        if missing:
            raise RegistryError(f"{cls.__name__} missing class attrs: {missing}")
        if cls.model_type not in (ModelType.TIME_STEPPED, ModelType.DISCRETE_EVENT):
            raise RegistryError(f"{cls.__name__}: invalid model_type {cls.model_type!r}")
        if not (isinstance(cls.model_type, str) and issubclass(cls, (DiscreteEventModel, TimeSteppedModel))):
            raise RegistryError(f"{cls.__name__}: model_type does not match base class")
        versions = self._by_id.setdefault(cls.model_id, {})
        if cls.version in versions:
            raise RegistryError(f"duplicate registration: {cls.model_id} v{cls.version}")
        versions[cls.version] = cls
        return cls

    def get(self, model_id: str, version: Optional[str] = None) -> Type[BaseWorldModel]:
        versions = self._by_id.get(model_id)
        if not versions:
            raise RegistryError(f"unknown model_id: {model_id!r}")
        if version is None:
            latest = max(versions)
            return versions[latest]
        if version not in versions:
            raise RegistryError(f"unknown version {version!r} for model {model_id!r}")
        return versions[version]

    def versions_of(self, model_id: str) -> list[str]:
        return sorted(self._by_id.get(model_id, {}))

    def list(self) -> list[dict[str, Any]]:
        out = []
        for model_id, versions in sorted(self._by_id.items()):
            for version, cls in sorted(versions.items()):
                out.append(
                    {
                        "model_id": model_id,
                        "version": version,
                        "display_name": cls.display_name,
                        "description": cls.description,
                        "model_type": cls.model_type,
                        "params_schema": cls.param_model.model_json_schema(),
                        "visualizer": cls.visualizer,
                    }
                )
        return out


registry = ModelRegistry()
