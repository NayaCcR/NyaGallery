from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

from nyagallery.plugins import PluginManifest


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    output: dict[str, object]


class PluginProcess:
    """Run a plugin entry module in a separate process with JSON line IPC.

    This is process isolation and timeout enforcement, not an OS-level syscall sandbox.
    """

    def __init__(self, manifest: PluginManifest, module_path: str | Path, *, timeout_seconds: float = 10.0, granted_permissions: Iterable[str] = ()) -> None:
        manifest.validate(core_version="999.0.0", granted_permissions=set(granted_permissions))
        self.manifest = manifest
        self.module_path = str(Path(module_path).resolve())
        self.timeout_seconds = max(0.1, timeout_seconds)
        self._process: subprocess.Popen[str] | None = None

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1", "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
        worker_path = str(Path(__file__).with_name("plugin_worker.py"))
        command = [sys.executable, worker_path, self.module_path]
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        return self._process

    def call(self, action: str) -> SandboxResult:
        process = self._ensure_process()
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("plugin process pipes are unavailable")
        process.stdin.write(json.dumps({"action": action}) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            detail = process.stderr.read().strip() if process.stderr is not None else ""
            raise RuntimeError(f"plugin process exited without a response{': ' + detail if detail else ''}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError("invalid plugin process response")
        return SandboxResult(ok=bool(payload.get("ok")), output=payload)

    def close(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.poll() is None:
                self.call("stop")
        except Exception:
            pass
        finally:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None
