"""Minimal third-party NyaGallery plugin.

Copy this folder to ``<storage>/plugins/hello-world`` and enable it in Admin -> Plugins.
plugin.json is authoritative for the manifest; this module only has to expose ``plugin``.
"""

from __future__ import annotations

from pathlib import Path

from nyagallery.plugins import PluginManifest

HERE = Path(__file__).resolve().parent


class HelloPlugin:
    # Overwritten from plugin.json by the host; kept here so the module is importable on its own.
    manifest = PluginManifest("community.hello", "0.1.0", ("analytics",), permissions=("routes", "events"))

    def setup(self, ctx) -> None:
        router = ctx.router()  # third-party routes always live under /api/plugins/<name>

        @router.get("/hello")
        def hello() -> dict[str, str]:
            return {"hello": "world"}

        ctx.on("plugin.enabled", self._log)
        ctx.on("plugin.disabled", self._log)

    def _log(self, payload: dict) -> None:
        with (HERE / "events.log").open("a", encoding="utf-8") as handle:
            handle.write(f"plugin.{'enabled' if payload.get('enabled', True) else 'disabled'} {payload.get('name')}\n")

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


plugin = HelloPlugin()
