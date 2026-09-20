"""Optional AI provider contracts. No model or network dependency is required."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AIResult:
    tags: tuple[str, ...] = ()
    description: str | None = None
    categories: tuple[str, ...] = ()
    scores: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NSFWResult:
    is_unsafe: bool
    score: float
    labels: dict[str, float] = field(default_factory=dict)
    provider: str = ""


class AIProvider(Protocol):
    name: str

    def analyze(self, image: Path | bytes, *, metadata: dict[str, Any] | None = None) -> AIResult: ...


class NSFWProvider(Protocol):
    name: str

    def classify(self, image: Path | bytes) -> NSFWResult: ...


class NullAIProvider:
    name = "none"

    def analyze(self, image: Path | bytes, *, metadata: dict[str, Any] | None = None) -> AIResult:
        return AIResult()


class NullNSFWProvider:
    name = "none"

    def classify(self, image: Path | bytes) -> NSFWResult:
        return NSFWResult(is_unsafe=False, score=0.0, provider=self.name)


def enforce_nsfw_policy(result: NSFWResult, *, threshold: float = 0.8) -> dict[str, Any]:
    threshold = max(0.0, min(1.0, float(threshold)))
    unsafe = bool(result.score >= threshold or result.is_unsafe)
    return {
        "status": "soft_deleted" if unsafe else "allowed",
        "is_unsafe": unsafe,
        "score": result.score,
        "threshold": threshold,
        "provider": result.provider,
        "labels": dict(result.labels),
    }
