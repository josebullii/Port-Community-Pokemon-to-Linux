"""Juegos de la biblioteca y el historial de sus lanzamientos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Game:
    """Un juego añadido a la biblioteca.

    ``id`` es también el nombre de su prefijo de Wine: así la CLI (``run``) y
    la interfaz usan el mismo prefijo, y con él las mismas partidas.
    """

    id: str
    name: str
    path: Path
    engine: str | None
    runtime: str | None
    bits: int | None
    added_at: datetime
    last_played_at: datetime | None = None
    play_seconds: float = 0.0
    """Tiempo total de juego (suma de la duración de los lanzamientos)."""
    launch_count: int = 0


@dataclass(frozen=True, slots=True)
class LaunchRecord:
    """Resultado de un lanzamiento, para el historial y la pantalla de detalles."""

    game_id: str
    started_at: datetime
    duration: float
    state: str
    """``ProcessState``: finished, crashed, stopped o failed."""
    exit_code: int | None = None
    error: str | None = None
    log_file: Path | None = None
    problems: tuple[str, ...] = ()
    """Identificadores de los problemas conocidos reconocidos en la salida."""
