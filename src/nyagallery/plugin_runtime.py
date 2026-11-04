from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
from typing import Callable

from nyagallery.plugins import PluginManifest


@dataclass
class RegisteredPlugin:
    manifest: PluginManifest
    start: Callable[[], None]
    stop: Callable[[], None]
    enabled: bool = False


class PluginRegistry:
    def __init__(self, *, core_version: str, permissions: set[str] | None = None, state_path: str | Path | None = None) -> None:
        self.core_version = core_version
        self.permissions = permissions or set()
        self.state_path = Path(state_path) if state_path else None
        self._plugins: dict[str, RegisteredPlugin] = {}

    def register(self, plugin: RegisteredPlugin) -> None:
        plugin.manifest.validate(core_version=self.core_version, granted_permissions=self.permissions)
        if plugin.manifest.name in self._plugins:
            raise ValueError(f"plugin already registered: {plugin.manifest.name}")
        self._plugins[plugin.manifest.name] = plugin

    def register_module(self, manifest: PluginManifest, module_path: str | Path) -> None:
        manifest.validate(core_version=self.core_version, granted_permissions=self.permissions)
        path = Path(module_path).resolve()
        spec = importlib.util.spec_from_file_location(f"nyagallery_plugin_{manifest.name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load plugin module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        start = getattr(module, "start", None)
        stop = getattr(module, "stop", None)
        if not callable(start) or not callable(stop):
            raise ValueError("plugin module must export start() and stop()")
        self.register(RegisteredPlugin(manifest=manifest, start=start, stop=stop))

    def enable(self, name: str) -> None:
        plugin = self._plugins[name]
        if plugin.enabled:
            return
        dependencies = set(plugin.manifest.dependencies)
        missing = [dependency for dependency in dependencies if dependency not in self._plugins or not self._plugins[dependency].enabled]
        if missing:
            raise RuntimeError(f"plugin dependencies are not enabled: {missing}")
        try:
            plugin.start()
        except Exception:
            plugin.enabled = False
            self.persist()
            raise
        plugin.enabled = True
        self.persist()

    def disable(self, name: str) -> None:
        plugin = self._plugins[name]
        dependents = [item.manifest.name for item in self._plugins.values() if item.enabled and name in item.manifest.dependencies]
        if dependents:
            raise RuntimeError(f"plugin has enabled dependents: {dependents}")
        if not plugin.enabled:
            return
        try:
            plugin.stop()
        finally:
            plugin.enabled = False
            self.persist()

    def snapshot(self) -> list[dict[str, object]]:
        return [{**plugin.manifest.to_dict(), "enabled": plugin.enabled} for plugin in self._plugins.values()]

    def persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def restore_enabled(self) -> None:
        if self.state_path is None or not self.state_path.is_file():
            return
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(saved, list):
            raise ValueError("plugin state must be a list")
        for item in saved:
            if isinstance(item, dict) and item.get("enabled") and str(item.get("name")) in self._plugins:
                self.enable(str(item["name"]))
