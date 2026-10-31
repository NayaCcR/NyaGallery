from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class WatchEvent:
    kind: str
    path: Path
    fingerprint: tuple[int, int]


class WatchImportBridge:
    def __init__(self, handler: Callable[[WatchEvent], None], *, conflict: str = "skip", delete_handler: Callable[[WatchEvent], None] | None = None) -> None:
        if conflict not in {"skip", "replace"}:
            raise ValueError("conflict must be skip or replace")
        self.handler = handler
        self.conflict = conflict
        self.delete_handler = delete_handler
        self._seen: set[Path] = set()

    def __call__(self, event: WatchEvent) -> None:
        if event.kind == "deleted":
            if self.delete_handler is not None:
                self.delete_handler(event)
            self._seen.discard(event.path)
            return
        if event.kind == "created" or self.conflict == "replace" or event.path not in self._seen:
            self.handler(event)
        self._seen.add(event.path)


class PollingWatcher:
    """Portable watch mode based on stable file fingerprints and a stoppable worker."""

    def __init__(self, root: str | Path, callback: Callable[[WatchEvent], None], *, interval: float = 2.0, suffixes: set[str] | None = None) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.root = Path(root).resolve()
        self.callback = callback
        self.interval = interval
        self.suffixes = {suffix.casefold() for suffix in suffixes} if suffixes else None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._snapshot: dict[Path, tuple[int, int]] = {}
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self.root.mkdir(parents=True, exist_ok=True)
            self._snapshot = self._scan()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="nyagallery-watch", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, timeout))
        with self._lock:
            if thread is self._thread and not self.running:
                self._thread = None

    def scan_once(self) -> list[WatchEvent]:
        current = self._scan()
        previous = self._snapshot
        events: list[WatchEvent] = []
        for path, fingerprint in current.items():
            if path not in previous:
                events.append(WatchEvent("created", path, fingerprint))
            elif previous[path] != fingerprint:
                events.append(WatchEvent("modified", path, fingerprint))
        for path, fingerprint in previous.items():
            if path not in current:
                events.append(WatchEvent("deleted", path, fingerprint))
        self._snapshot = current
        for event in sorted(events, key=lambda item: str(item.path)):
            self._dispatch(event)
        return events

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.scan_once()
            except Exception as exc:  # callback and filesystem errors must not kill watch mode
                self.last_error = str(exc)

    def _dispatch(self, event: WatchEvent) -> None:
        try:
            self.callback(event)
        except Exception as exc:
            self.last_error = str(exc)

    def _scan(self) -> dict[Path, tuple[int, int]]:
        if not self.root.exists():
            return {}
        result: dict[Path, tuple[int, int]] = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or (self.suffixes is not None and path.suffix.casefold() not in self.suffixes):
                continue
            stat = path.stat()
            result[path] = (stat.st_size, stat.st_mtime_ns)
        return result
