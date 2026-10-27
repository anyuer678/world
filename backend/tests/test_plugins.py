import sys
import textwrap
from pathlib import Path

import pytest

from app.core.plugins import PluginError, load_plugin_modules
from app.core.registry import ModelRegistry, RegistryError


def _minimal_cls_attrs(**overrides):
    attrs = {
        "model_id": "plug_x",
        "display_name": "Plug X",
        "description": "Test plugin model.",
        "model_type": "time_stepped",
        "version": "1.0.0",
        "__annotations__": {},
    }
    attrs.update(overrides)
    return attrs


def _make_cls(registry, base, param_model, **overrides):
    attrs = _minimal_cls_attrs(**overrides)
    attrs["param_model"] = param_model

    class PlugModel(base):
        def initialize(self, ctx):
            pass

        def dump_state(self):
            return {}

        def load_state(self, state):
            pass

        def snapshot(self):
            return {}

        def finalize_metrics(self):
            return {}

        def step(self):
            pass

    for k, v in attrs.items():
        setattr(PlugModel, k, v)
    return registry.register(PlugModel)


def _param_model():
    from app.core.engine.models_base import WorldLabParams

    class P(WorldLabParams):
        n: int = 1

    return P


def test_register_rejects_missing_description():
    reg = ModelRegistry()
    with pytest.raises(RegistryError, match="description"):
        _make_cls(reg, __import__("app.core.engine.models_base", fromlist=["TimeSteppedModel"]).TimeSteppedModel, _param_model(), description="")


def test_register_rejects_bad_visualizer():
    reg = ModelRegistry()
    with pytest.raises(RegistryError, match="visualizer"):
        _make_cls(reg, __import__("app.core.engine.models_base", fromlist=["TimeSteppedModel"]).TimeSteppedModel, _param_model(), visualizer={"kind": 3})


def test_register_rejects_model_type_mismatch():
    reg = ModelRegistry()
    from app.core.engine.models_base import DiscreteEventModel

    with pytest.raises(RegistryError, match="model_type"):
        _make_cls(reg, DiscreteEventModel, _param_model())


def test_load_plugin_modules_via_register_hook(tmp_path: Path, monkeypatch):
    plugin_dir = tmp_path / "wlplugtest"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "model.py").write_text(
        textwrap.dedent(
            """
            from app.core.engine.models_base import TimeSteppedModel, WorldLabParams
            from pydantic import ConfigDict


            class PlugParams(WorldLabParams):
                model_config = ConfigDict(extra="forbid")
                n: int = 3


            class PlugStepModel(TimeSteppedModel):
                model_id = "plug_ext_step"
                display_name = "External plug"
                description = "External plugin loaded in test."
                model_type = "time_stepped"
                version = "1.0.0"
                visualizer = {"kind": "series", "series": ["n"]}
                param_model = PlugParams

                def initialize(self, ctx):
                    self.count = self.params.n

                def dump_state(self):
                    return {"count": self.count}

                def load_state(self, state):
                    self.count = state["count"]

                def snapshot(self):
                    return {"count": self.count}

                def finalize_metrics(self):
                    return {"count": float(self.count)}

                def step(self):
                    self.count -= 1


            def register(registry):
                registry.register(PlugStepModel)
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    reg = ModelRegistry()
    loaded = load_plugin_modules(["wlplugtest.model"], reg)
    assert loaded == ["wlplugtest.model"]
    cls = reg.get("plug_ext_step")
    assert cls.display_name == "External plug"
    inst = cls({"n": 5}, rng_seed=1)
    inst.initialize(None)
    inst.step()
    assert inst.finalize_metrics() == {"count": 4.0}


def test_load_plugin_modules_unknown_module():
    with pytest.raises(PluginError, match="could not be imported"):
        load_plugin_modules(["definitely_not_a_module_xyz"], ModelRegistry())


def test_load_plugin_modules_hook_failure(tmp_path: Path, monkeypatch):
    pkg = tmp_path / "badplugmod"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "def register(registry):\n    raise ValueError('boom')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(PluginError, match="boom"):
        load_plugin_modules(["badplugmod"], ModelRegistry())
