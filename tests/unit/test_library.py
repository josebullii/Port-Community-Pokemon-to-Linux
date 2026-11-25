from datetime import UTC, datetime
from pathlib import Path

import pytest

from pokemon_to_linux.application.analyze_game import analyze_game
from pokemon_to_linux.application.diagnose_output import GENERIC_ISSUES, Finding
from pokemon_to_linux.application.library import Library, LibraryError, inspect_game
from pokemon_to_linux.domain.game import Game
from pokemon_to_linux.domain.profile import parse_profile
from pokemon_to_linux.infrastructure.database.connection import open_database
from pokemon_to_linux.infrastructure.database.game_repository import GameRepository
from pokemon_to_linux.infrastructure.system.host import HostSystem
from pokemon_to_linux.infrastructure.wine.process_manager import LaunchOutcome, ProcessState

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

PROFILE = parse_profile(
    {
        "schema": 1,
        "id": "prueba",
        "name": "Juego de prueba",
        "match": {"titles": ["Juego de prueba"]},
        "saves": {"paths": ["%USERPROFILE%/Saved Games/Prueba"]},
    },
    "prueba.toml",
)


@pytest.fixture
def library():
    conn = open_database(":memory:")
    yield Library(GameRepository(conn), clock=lambda: NOW)
    conn.close()


def host():
    h = HostSystem(env={"DISPLAY": ":0"}, x11_socket_dir=None)
    h.__dict__["shared_libraries"] = {"libGL.so.1": {32, 64}}
    return h


# --- Añadir y quitar ----------------------------------------------------------


def test_add_game(library, make_game):
    folder = make_game(exe="mkxp-z")

    game = library.add(analyze_game(folder))

    assert game.id == "juego-de-prueba"
    assert game.name == "Juego de prueba"
    assert game.path == folder.resolve()
    assert (game.engine, game.runtime, game.bits) == ("rpgmaker_xp", "mkxp-z", 32)
    assert game.added_at == NOW
    assert library.games() == [game]


def test_add_rejects_unknown_engine(library, tmp_path):
    with pytest.raises(LibraryError, match="No se reconoce el motor"):
        library.add(analyze_game(tmp_path))


def test_add_rejects_the_same_folder_twice(library, make_game):
    folder = make_game()
    library.add(analyze_game(folder))

    with pytest.raises(LibraryError, match="ya está en la biblioteca como «Juego de prueba»"):
        library.add(analyze_game(folder))


def test_two_copies_of_a_game_get_their_own_prefix(library, make_game):
    """Mismo título, carpetas distintas: cada copia con su id (y su prefijo)."""
    first = library.add(analyze_game(make_game()))
    second = library.add(analyze_game(make_game()))
    third = library.add(analyze_game(make_game()))

    assert [first.id, second.id, third.id] == [
        "juego-de-prueba",
        "juego-de-prueba-2",
        "juego-de-prueba-3",
    ]


def test_rename_and_remove(library, make_game):
    game = library.add(analyze_game(make_game()))

    assert library.rename(game.id, "  Mi juego  ").name == "Mi juego"
    with pytest.raises(LibraryError, match="vacío"):
        library.rename(game.id, "   ")

    library.remove(game.id)
    assert library.games() == []
    with pytest.raises(LibraryError, match="No hay ningún juego"):
        library.remove(game.id)


def test_remove_keeps_the_game_folder(library, make_game):
    folder = make_game()
    library.remove(library.add(analyze_game(folder)).id)
    assert (folder / "Game.exe").is_file()


# --- Historial ----------------------------------------------------------------


def test_record_launch(library, make_game):
    game = library.add(analyze_game(make_game()))
    opengl = next(i for i in GENERIC_ISSUES if i.id == "opengl-sin-formato")
    outcome = LaunchOutcome(game.id, ProcessState.CRASHED, 1, 90.0, "se cerró", Path("/logs/1.log"))
    findings = [Finding(opengl, "Failed to load libGL"), Finding(opengl, "otra línea")]

    record = library.record_launch(game.id, outcome, findings)

    assert record.started_at == datetime(2026, 11, 26, 11, 58, 30, tzinfo=UTC)
    assert record.state == "crashed"
    assert record.problems == ("opengl-sin-formato",)
    assert library.history(game.id) == [record]
    stored = library.get(game.id)
    assert stored.launch_count == 1
    assert stored.play_seconds == 90.0


# --- Detalles -----------------------------------------------------------------


def test_inspect_game_without_prefix(make_game, tmp_path):
    folder = make_game(exe="mkxp-z")
    game = Game("juego-de-prueba", "Juego", folder, "rpgmaker_xp", "mkxp-z", 32, NOW)

    details = inspect_game(game, profiles=[PROFILE], prefixes_dir=tmp_path / "p", host=host())

    assert details.error is None
    assert details.profile is PROFILE
    assert [c.id for c in details.checks] == ["display", "opengl", "filesystem"]
    assert details.ready
    assert details.prefix_path is None
    assert details.save_dirs == ()


def test_inspect_game_with_prefix_resolves_saves(make_game, tmp_path):
    folder = make_game(exe="mkxp-z")
    prefix = tmp_path / "p" / "juego-de-prueba"
    (prefix / "drive_c" / "users" / "jose").mkdir(parents=True)
    (prefix / "system.reg").write_text("WINE REGISTRY Version 2\n#arch=win64\n")
    game = Game("juego-de-prueba", "Juego", folder, "rpgmaker_xp", "mkxp-z", 32, NOW)

    details = inspect_game(game, profiles=[PROFILE], prefixes_dir=tmp_path / "p", host=host())

    assert details.prefix_path == prefix
    assert details.save_dirs == (prefix / "drive_c" / "users" / "jose" / "Saved Games" / "Prueba",)


def test_inspect_game_whose_folder_is_gone(tmp_path):
    game = Game("x", "X", tmp_path / "no-existe", "rpgmaker_xp", None, 32, NOW)

    details = inspect_game(game, profiles=[], prefixes_dir=tmp_path, host=host())

    assert details.analysis is None
    assert "No se puede leer la carpeta" in details.error
    assert not details.ready


def test_inspect_game_whose_folder_changed(tmp_path):
    (tmp_path / "vacia").mkdir()
    game = Game("x", "X", tmp_path / "vacia", "rpgmaker_xp", None, 32, NOW)

    details = inspect_game(game, profiles=[], prefixes_dir=tmp_path, host=host())

    assert "ya no contiene un juego" in details.error
    assert not details.ready


def test_inspect_game_not_ready_without_opengl(make_game, tmp_path):
    folder = make_game(exe="mkxp-z")
    game = Game("j", "J", folder, "rpgmaker_xp", "mkxp-z", 32, NOW)
    no_gl = HostSystem(env={"DISPLAY": ":0"}, x11_socket_dir=None)
    no_gl.__dict__["shared_libraries"] = {}

    details = inspect_game(game, profiles=[], prefixes_dir=tmp_path, host=no_gl)

    assert not details.ready
