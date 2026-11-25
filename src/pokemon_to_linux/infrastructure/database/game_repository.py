"""Repositorio de juegos y lanzamientos sobre SQLite.

Las fechas se guardan como texto ISO 8601 en UTC. Las rutas, como texto
absoluto. Un ``sqlite3.Connection`` solo se usa desde el hilo que lo abrió:
en la interfaz, el hilo principal.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pokemon_to_linux.domain.game import Game, LaunchRecord

_GAME_QUERY = """
    SELECT g.id, g.name, g.path, g.engine, g.runtime, g.bits, g.added_at,
           MAX(l.started_at) AS last_played_at,
           COALESCE(SUM(l.duration), 0) AS play_seconds,
           COUNT(l.id) AS launch_count
    FROM games g LEFT JOIN launches l ON l.game_id = g.id
"""
"""Juegos con los totales de su historial. Texto fijo: los valores van siempre con ``?``."""


class DuplicateGameError(ValueError):
    """Ya hay un juego con ese identificador o esa carpeta."""


def _to_text(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("las fechas deben llevar zona horaria")
    return moment.astimezone(UTC).isoformat()


def _from_text(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _game(row: sqlite3.Row) -> Game:
    return Game(
        id=row["id"],
        name=row["name"],
        path=Path(row["path"]),
        engine=row["engine"],
        runtime=row["runtime"],
        bits=row["bits"],
        added_at=_from_text(row["added_at"]),
        last_played_at=_from_text(row["last_played_at"]),
        play_seconds=float(row["play_seconds"]),
        launch_count=int(row["launch_count"]),
    )


def _launch(row: sqlite3.Row) -> LaunchRecord:
    return LaunchRecord(
        game_id=row["game_id"],
        started_at=_from_text(row["started_at"]),
        duration=float(row["duration"]),
        state=row["state"],
        exit_code=row["exit_code"],
        error=row["error"],
        log_file=Path(row["log_file"]) if row["log_file"] else None,
        problems=tuple(p for p in row["problems"].split(",") if p),
    )


class GameRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- Juegos -------------------------------------------------------------

    def add(self, game: Game) -> Game:
        if self.get(game.id) is not None:
            raise DuplicateGameError(f"Ya hay un juego con el identificador {game.id}")
        if (other := self.get_by_path(game.path)) is not None:
            raise DuplicateGameError(f"Esa carpeta ya está en la biblioteca como «{other.name}»")
        self._conn.execute(
            "INSERT INTO games (id, name, path, engine, runtime, bits, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (game.id, game.name, str(game.path), game.engine, game.runtime, game.bits,
             _to_text(game.added_at)),
        )  # fmt: skip
        return self.get(game.id)

    def get(self, game_id: str) -> Game | None:
        row = self._conn.execute(f"{_GAME_QUERY} WHERE g.id = ? GROUP BY g.id", (game_id,))
        return _game(r) if (r := row.fetchone()) else None

    def get_by_path(self, path: Path) -> Game | None:
        row = self._conn.execute(f"{_GAME_QUERY} WHERE g.path = ? GROUP BY g.id", (str(path),))
        return _game(r) if (r := row.fetchone()) else None

    def list(self) -> list[Game]:
        rows = self._conn.execute(f"{_GAME_QUERY} GROUP BY g.id ORDER BY g.name COLLATE NOCASE")
        return [_game(r) for r in rows]

    def rename(self, game_id: str, name: str) -> None:
        self._conn.execute("UPDATE games SET name = ? WHERE id = ?", (name, game_id))

    def remove(self, game_id: str) -> bool:
        """Quita el juego y su historial. No toca la carpeta del juego ni su prefijo."""
        return self._conn.execute("DELETE FROM games WHERE id = ?", (game_id,)).rowcount > 0

    # --- Lanzamientos -------------------------------------------------------

    def record_launch(self, record: LaunchRecord) -> None:
        self._conn.execute(
            "INSERT INTO launches (game_id, started_at, duration, state, exit_code, error, "
            "log_file, problems) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.game_id,
                _to_text(record.started_at),
                record.duration,
                record.state,
                record.exit_code,
                record.error,
                str(record.log_file) if record.log_file else None,
                ",".join(record.problems),
            ),
        )

    def launches(self, game_id: str, limit: int = 20) -> Sequence[LaunchRecord]:
        """Los últimos lanzamientos del juego, del más reciente al más antiguo."""
        rows = self._conn.execute(
            "SELECT * FROM launches WHERE game_id = ? ORDER BY started_at DESC, id DESC LIMIT ?",
            (game_id, limit),
        )
        return [_launch(r) for r in rows]
