"""Selección del motor de un juego entre los detectores disponibles."""

from __future__ import annotations

from collections.abc import Sequence

from pokemon_to_linux.engines.base import DetectionResult, EngineDetector
from pokemon_to_linux.engines.rpgmaker_xp.detector import RPGMakerXPDetector
from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScan


def default_detectors() -> tuple[EngineDetector, ...]:
    return (RPGMakerXPDetector(),)


def detect_engine(
    scan: GameScan, detectors: Sequence[EngineDetector] | None = None
) -> DetectionResult:
    """Ejecuta todos los detectores y devuelve el mejor resultado.

    Gana el detectado con más confianza. Si ninguno detecta nada, se devuelve
    el de más confianza (con ``detected=False``) para conservar sus indicios.
    """
    detectors = default_detectors() if detectors is None else detectors
    results = [d.detect(scan) for d in detectors]
    if not results:
        return DetectionResult(engine="unknown", detected=False, confidence=0.0)
    return max(results, key=lambda r: (r.detected, r.confidence))
