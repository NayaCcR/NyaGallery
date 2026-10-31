from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable


class ImportJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class ImportJob:
    job_id: str
    total: int = 0
    cursor: int = 0
    succeeded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    failed_indices: set[int] = field(default_factory=set)
    status: ImportJobStatus = ImportJobStatus.QUEUED

    @property
    def progress(self) -> float:
        return 100.0 if self.total == 0 and self.status == ImportJobStatus.SUCCEEDED else (self.cursor / self.total * 100.0 if self.total else 0.0)

    def checkpoint(self) -> dict[str, object]:
        return {"job_id": self.job_id, "total": self.total, "cursor": self.cursor, "succeeded": self.succeeded, "failed": self.failed, "errors": list(self.errors), "failed_indices": sorted(self.failed_indices), "status": self.status.value, "progress": self.progress}

    def pause(self) -> None:
        if self.status == ImportJobStatus.RUNNING:
            self.status = ImportJobStatus.PAUSED

    def resume(self) -> None:
        if self.status in {ImportJobStatus.QUEUED, ImportJobStatus.PAUSED, ImportJobStatus.FAILED}:
            self.status = ImportJobStatus.RUNNING

    def run_source(self, source: object, handler: Callable[[object], None], *, retry_failed: bool = False) -> dict[str, object]:
        items = source.iter_items()
        return self.run(items, handler, retry_failed=retry_failed)

    def run(self, items: Iterable[object], handler: Callable[[object], None], *, retry_failed: bool = False) -> dict[str, object]:
        values = list(items)
        if self.total == 0:
            self.total = len(values)
        if self.status == ImportJobStatus.PAUSED:
            return self.checkpoint()
        self.resume()
        indices = sorted(self.failed_indices) if retry_failed else range(min(self.cursor, len(values)), len(values))
        for index in indices:
            if self.status == ImportJobStatus.PAUSED:
                break
            try:
                handler(values[index])
                self.succeeded += 1
                self.failed_indices.discard(index)
                self.cursor = max(self.cursor, index + 1)
            except Exception as exc:
                self.failed += 1
                self.failed_indices.add(index)
                self.errors.append(f"{index}: {exc}")
                self.cursor = max(self.cursor, index + 1)
        if self.status != ImportJobStatus.PAUSED:
            self.status = ImportJobStatus.FAILED if self.failed else ImportJobStatus.SUCCEEDED
        return self.checkpoint()
