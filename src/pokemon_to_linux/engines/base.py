"""Contrato común de los detectores de motor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScan

DETECTION_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Evidence:
    """Un indicio considerado por el detector y su peso (negativo = en contra)."""

    indicator: str
    detail: str
    weight: float


@dataclass(frozen=True, slots=True)
class DetectionResult:
    engine: str
    detected: bool
    confidence: float
    executable: str | None = None
    runtime: str = "unknown"
    warnings: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Esquema de la guía (detected, engine, confidence, executable, runtime,
        warnings) ampliado con ``evidence`` y ``details``."""
        return {
            "detected": self.detected,
            "engine": self.engine,
            "confidence": round(self.confidence, 2),
            "executable": self.executable,
            "runtime": self.runtime,
            "warnings": list(self.warnings),
            "evidence": [
                {"indicator": e.indicator, "detail": e.detail, "weight": e.weight}
                for e in self.evidence
            ],
            "details": dict(self.details),
        }


class EngineDetector(ABC):
    engine_id: str
    display_name: str

    @abstractmethod
    def detect(self, scan: GameScan) -> DetectionResult: ...
