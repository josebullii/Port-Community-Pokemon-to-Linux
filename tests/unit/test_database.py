import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pokemon_to_linux.domain.game import Game, LaunchRecord
from pokemon_to_linux.infrastructure.database.connection import (
    SCHEMA_VERSION,
    DatabaseError,
    migrate,
    open_database,
    schema_version,
)
from pokemon_to_linux.infrastructure.database.game_repository import (
    DuplicateGameError,
    GameRepository,
)

NOW = datetime(2026, 11, 25, 18, 0, tzinfo=UTC)


def game(game_id="pokemon-z", name="Pokemon Z", path="/juegos/Pokemon Z", **kw):
    data = {"engine": "rpgmaker_xp", "runtime": "mkxp-z", "bits": 32, "added_at": NOW}
    data.update(kw)
    return Game(game_id, name, Path(path), **data)


@pytest.fixture
def repo():
    conn = open_database(":memory:")
    yield GameRepository(conn)
    conn.close()


# --- Conexión y migraciones ---------------------------------------------------


def test_new_database_has_the_latest_schema(tmp_path):
    path = tmp_path / "sub" / "library.sqlite3"
    conn = open_database(path)
    assert schema_version(conn) == SCHEMA_VERSION
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()

    # Reabrirla no vuelve a aplicar nada.
    conn = open_database(path)
    assert schema_version(conn) == SCHEMA_VERSION
    conn.close()


def test_failed_migration_leaves_previous_version():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    migrations = ("CREATE TABLE a (x INTEGER)", "CREATE TABLE b (x INTEGER); NO ES SQL")

    with pytest.raises(DatabaseError, match="versión 2"):
        migrate(conn, migrations)

    assert schema_version(conn) == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'b'").fetchone() is None


def test_newer_database_is_not_touched(tmp_path):
    path = tmp_path / "library.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()

    with pytest.raises(DatabaseError, match="versión más nueva"):
        open_database(path)


def test_corrupt_file_is_reported(tmp_path):
    path = tmp_path / "library.sqlite3"
    path.write_bytes(b"esto no es una base de datos" * 100)

    with pytest.raises(DatabaseError, match="dañada"):
        open_database(path)


# --- Juegos -------------------------------------------------------------------


def test_add_and_get(repo):
    added = repo.add(game())

    assert added == game()
    assert repo.get("pokemon-z") == added
    assert repo.get_by_path(Path("/juegos/Pokemon Z")) == added
    assert repo.get("otro") is None
    assert added.added_at == NOW
    assert added.launch_count == 0
    assert added.last_played_at is None


def test_duplicates_are_rejected(repo):
    repo.add(game())

    with pytest.raises(DuplicateGameError, match="identificador"):
        repo.add(game(path="/otra"))
    with pytest.raises(DuplicateGameError, match="ya está en la biblioteca como «Pokemon Z»"):
        repo.add(game(game_id="otro"))


def test_list_is_sorted_by_name(repo):
    repo.add(game("b", "pokémon zeta", "/b"))
    repo.add(game("a", "Pokemon Insurgence", "/a"))
    repo.add(game("c", "Aventura", "/c"))

    assert [g.id for g in repo.list()] == ["c", "a", "b"]


def test_rename_and_remove(repo):
    repo.add(game())
    repo.record_launch(LaunchRecord("pokemon-z", NOW, 10, "finished", 0))

    repo.rename("pokemon-z", "Pokémon Z 2.19")
    assert repo.get("pokemon-z").name == "Pokémon Z 2.19"

    assert repo.remove("pokemon-z") is True
    assert repo.get("pokemon-z") is None
    assert repo.launches("pokemon-z") == []
    assert repo.remove("pokemon-z") is False


def test_dates_must_have_a_timezone(repo):
    with pytest.raises(ValueError, match="zona horaria"):
        repo.add(game(added_at=datetime(2026, 1, 1)))  # noqa: DTZ001


# --- Lanzamientos -------------------------------------------------------------


def test_launch_history_and_totals(repo):
    repo.add(game())
    first = LaunchRecord("pokemon-z", NOW, 60.5, "finished", 0)
    second = LaunchRecord(
        "pokemon-z",
        NOW + timedelta(hours=1),
        30,
        "crashed",
        None,
        error="se cerró",
        log_file=Path("/logs/x.log"),
        problems=("opengl-sin-formato", "audio-no-disponible"),
    )
    repo.record_launch(first)
    repo.record_launch(second)

    assert repo.launches("pokemon-z") == [second, first]
    assert repo.launches("pokemon-z", limit=1) == [second]
    stored = repo.get("pokemon-z")
    assert stored.launch_count == 2
    assert stored.play_seconds == pytest.approx(90.5)
    assert stored.last_played_at == NOW + timedelta(hours=1)


def test_launch_of_unknown_game_is_rejected(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.record_launch(LaunchRecord("no-existe", NOW, 1, "finished", 0))
