"""Caso de uso: analizar la carpeta de un juego y diagnosticar su motor."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokemon_to_linux.engines.base import DetectionResult, EngineDetector
from pokemon_to_linux.engines.detector import default_detectors, detect_engine
from pokemon_to_linux.infrastructure.filesystem.game_scanner import (
    GameScan,
    GameScanError,
    GameScanner,
)
from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

__all__ = ["GameAnalysis", "GameScanError", "analyze_game", "engine_display_name"]


def engine_display_name(engine_id: str) -> str:
    names = {d.engine_id: d.display_name for d in default_detectors()}
    return names.get(engine_id, "Desconocido")


@dataclass(frozen=True, slots=True)
class GameAnalysis:
    scan: GameScan
    detection: DetectionResult
    warnings: tuple[str, ...]
    """Advertencias del escaneo seguidas de las del detector."""

    @property
    def path(self) -> Path:
        return self.scan.root

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"game_path": str(self.path)}
        data.update(self.detection.to_dict())
        data["warnings"] = list(self.warnings)
        data["scan"] = {
            "total_files": self.scan.total_files,
            "total_size_bytes": self.scan.total_size,
            "top_extensions": dict(list(self.scan.extension_counts.items())[:8]),
            "truncated": self.scan.truncated,
            "skipped_symlinks": list(self.scan.skipped_symlinks),
            "unreadable": list(self.scan.unreadable),
        }
        return data


def analyze_game(
    path: Path | str,
    *,
    scanner: GameScanner | None = None,
    detectors: Sequence[EngineDetector] | None = None,
) -> GameAnalysis:
    """Escanea ``path`` y detecta el motor. Lanza ``GameScanError`` si la ruta no vale."""
    scanner = scanner or GameScanner()
    scan = scanner.scan(path)
    detection = detect_engine(scan, detectors)

    warnings: list[str] = []
    if scan.truncated:
        warnings.append(
            f"La carpeta tiene más de {scanner.max_files} ficheros; el análisis es parcial."
        )
    if scan.skipped_symlinks:
        warnings.append(
            "Se han ignorado enlaces simbólicos por seguridad: "
            + ", ".join(scan.skipped_symlinks[:5])
            + (" …" if len(scan.skipped_symlinks) > 5 else "")
        )
    if scan.unreadable:
        warnings.append(
            "No se han podido leer algunos ficheros o carpetas: "
            + ", ".join(scan.unreadable[:5])
            + (" …" if len(scan.unreadable) > 5 else "")
        )
    warnings.extend(detection.warnings)

    log.info(
        "Análisis de %s: motor=%s detectado=%s confianza=%.2f runtime=%s",
        scan.root,
        detection.engine,
        detection.detected,
        detection.confidence,
        detection.runtime,
    )
    return GameAnalysis(scan=scan, detection=detection, warnings=tuple(warnings))
