"""External plugin loading. Operator-installed Python packages can register
model classes the same way built-ins do, without touching app code.

Contract: each plugin module either registers via import side effects, or
(better) defines ``register(registry)`` which is called with the active
registry. Plugin code runs in the server process, so it carries the same
trust level as any other installed dependency - untrusted code is never
supported (specs define behaviour, not code; see docs/PLUGINS.md).
"""
from __future__ import annotations

import importlib
from typing import Iterable

from .registry import ModelRegistry, RegistryError


class PluginError(RegistryError):
    pass


def load_plugin_modules(module_names: Iterable[str], registry: ModelRegistry | None = None) -> list[str]:
    """Import plugin modules in order and invoke their register() hook.

    Returns the list of module names actually loaded. Raises PluginError on
    the first failure; already-loaded modules are not rolled back.
    """
    target = registry
    if target is None:
        from .registry import registry as default_registry

        target = default_registry
    loaded: list[str] = []
    for name in module_names:
        name = name.strip()
        if not name:
            continue
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            raise PluginError(f"plugin module {name!r} could not be imported: {exc}") from exc
        hook = getattr(module, "register", None)
        if callable(hook):
            try:
                hook(target)
            except Exception as exc:
                raise PluginError(f"plugin module {name!r} register() failed: {exc}") from exc
        loaded.append(name)
    return loaded
