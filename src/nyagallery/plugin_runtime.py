from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from nyagallery.plugins import PluginManifest


@dataclass
class RegisteredPlugin:
    manifest: PluginManifest
    start: Callable[[], None]
    stop: Callable[[], None]
    enabled: bool = False


class PluginRegistry:
    def __init__(self, *, core_version: str, permissions: set[str] | None = None) -> None:
        self.core_version = core_version
        self.permissions = permissions or set()
        self._plugins: dict[str, RegisteredPlugin] = {}

    def register(self, plugin: RegisteredPlugin) -> None:
        plugin.manifest.validate(core_version=self.core_version, granted_permissions=self.permissions)
        if plugin.manifest.name in self._plugins:
            raise ValueError(f"plugin already registered: {plugin.manifest.name}")
        self._plugins[plugin.manifest.name] = plugin

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
            raise
        plugin.enabled = True

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

    def snapshot(self) -> list[dict[str, object]]:
        return [{**plugin.manifest.to_dict(), "enabled": plugin.enabled} for plugin in self._plugins.values()]
