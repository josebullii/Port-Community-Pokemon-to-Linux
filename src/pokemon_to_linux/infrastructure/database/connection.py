"""Conexión SQLite de la biblioteca y migraciones del esquema.

La versión del esquema se guarda en ``PRAGMA user_version``. Cada migración
se aplica en su propia transacción: si falla, la base de datos queda en la
versión anterior. Una base de datos de una versión más nueva de la
aplicación no se toca.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class DatabaseError(RuntimeError):
    pass


MIGRATIONS: tuple[str, ...] = (
    # 1: juegos e historial de lanzamientos (sprint 5).
    """
    CREATE TABLE games (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        path          TEXT NOT NULL UNIQUE,
        engine        TEXT,
        runtime       TEXT,
        bits          INTEGER,
        added_at      TEXT NOT NULL
    );
    CREATE TABLE launches (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id       TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        started_at    TEXT NOT NULL,
        duration      REAL NOT NULL,
        state         TEXT NOT NULL,
        exit_code     INTEGER,
        error         TEXT,
        log_file      TEXT,
        problems      TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX launches_by_game ON launches(game_id, started_at);
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)


def open_database(path: Path | str) -> sqlite3.Connection:
    """Abre (o crea) la base de datos y la deja en la última versión del esquema.

    ``":memory:"`` sirve para las pruebas.
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path), isolation_level=None)
    except sqlite3.Error as exc:
        raise DatabaseError(f"No se puede abrir la base de datos {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        migrate(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection, migrations: tuple[str, ...] = MIGRATIONS) -> None:
    try:
        current = schema_version(conn)
    except sqlite3.DatabaseError as exc:
        raise DatabaseError(f"La base de datos está dañada o no es SQLite: {exc}") from exc
    if current > len(migrations):
        raise DatabaseError(
            f"La biblioteca es de una versión más nueva de la aplicación (esquema "
            f"{current}, esta admite hasta {len(migrations)}). Actualiza la aplicación."
        )
    for version in range(current + 1, len(migrations) + 1):
        try:
            conn.execute("BEGIN")
            for statement in _statements(migrations[version - 1]):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version:d}")
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise DatabaseError(
                f"No se pudo actualizar la biblioteca a la versión {version}: {exc}"
            ) from exc
        log.info("Base de datos actualizada al esquema %d", version)


def _statements(script: str) -> list[str]:
    # executescript() haría COMMIT por su cuenta y rompería la transacción.
    return [s.strip() for s in script.split(";") if s.strip()]
