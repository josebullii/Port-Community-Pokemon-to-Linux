from pathlib import Path

import pytest
from test_prefix_manager import WINE, FakeWine

from pokemon_to_linux.application.launch_game import (
    GAME_WINEDEBUG,
    MISSING_32_BIT_HINT,
    LaunchError,
    prepare_launch,
)
from pokemon_to_linux.domain.profile import GameProfile, ProfileMatch
from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixError, PrefixManager


@pytest.fixture
def prefixes(tmp_path):
    return tmp_path / "prefixes"


def pm(prefixes, fake):
    return PrefixManager(prefixes, WINE, runner=fake, registry_wait=0.2)


def test_plan_for_xp_game(make_game, prefixes):
    game = make_game(exe="runnable")
    fake = FakeWine()

    plan = prepare_launch(game, wine=WINE, prefixes=pm(prefixes, fake))

    assert plan.game_id == "juego-de-prueba"  # del Title de Game.ini
    assert plan.prefix.arch == "win64"
    assert plan.prefix_created is True
    assert plan.test_result.ok and plan.test_result.bits == 32
    spec = plan.spec
    assert spec.program == WINE.wine
    assert spec.arguments == (str(game.resolve() / "Game.exe"),)
    assert spec.working_dir == game.resolve()
    assert spec.environment["WINEPREFIX"] == str(prefixes / "juego-de-prueba")
    assert spec.stop_command == (str(WINE.wineserver), "-k")


def test_existing_prefix_is_reused_without_test(make_game, prefixes):
    game = make_game(exe="runnable")
    fake = FakeWine()
    prepare_launch(game, wine=WINE, prefixes=pm(prefixes, fake))

    plan = prepare_launch(game, wine=WINE, prefixes=pm(prefixes, fake))

    assert plan.prefix_created is False
    assert plan.test_result is None


def test_custom_id_arch_and_env(make_game, prefixes):
    plan = prepare_launch(
        make_game(exe="runnable"),
        wine=WINE,
        prefixes=pm(prefixes, FakeWine()),
        game_id="mi-juego",
        arch="win32",
        extra_env={"LANG": "es_ES.UTF-8"},
    )

    assert plan.game_id == "mi-juego"
    assert plan.prefix.arch == "win32"
    assert plan.spec.environment["LANG"] == "es_ES.UTF-8"


def test_missing_32_bit_support_gives_clear_error(make_game, prefixes):
    fake = FakeWine(program_code=1)  # el programa de prueba de 32 bits falla

    with pytest.raises(LaunchError) as exc:
        prepare_launch(make_game(exe="runnable"), wine=WINE, prefixes=pm(prefixes, fake))

    assert "32 bits" in str(exc.value)
    assert MISSING_32_BIT_HINT in str(exc.value)


def test_failed_check_removes_prefix_so_next_attempt_checks_again(make_game, prefixes):
    """Regresión: el prefijo que no superaba la comprobación se reutilizaba sin comprobar."""
    game = make_game(exe="runnable")
    fake = FakeWine(program_code=1)

    for _ in range(2):  # el segundo intento debe fallar igual, no lanzar el juego
        with pytest.raises(LaunchError, match="32 bits"):
            prepare_launch(game, wine=WINE, prefixes=pm(prefixes, fake))
        assert not (prefixes / "juego-de-prueba").exists()

    # Con Wine ya arreglado, el siguiente intento crea y comprueba un prefijo nuevo.
    fake.program_code = 42
    plan = prepare_launch(game, wine=WINE, prefixes=pm(prefixes, fake))
    assert plan.prefix_created is True
    assert plan.test_result.ok


def test_unknown_engine_is_rejected(tmp_path, prefixes):
    with pytest.raises(LaunchError, match="motor"):
        prepare_launch(tmp_path, wine=WINE, prefixes=pm(prefixes, FakeWine()))


def test_game_without_executable_is_rejected(make_game, prefixes):
    with pytest.raises(LaunchError, match="ejecutable"):
        prepare_launch(make_game(exe=None), wine=WINE, prefixes=pm(prefixes, FakeWine()))


def test_invalid_game_id_is_rejected(make_game, prefixes):
    with pytest.raises(PrefixError, match="no válido"):
        prepare_launch(
            make_game(exe="runnable"),
            wine=WINE,
            prefixes=pm(prefixes, FakeWine()),
            game_id="../fuera",
        )


def test_without_wineserver_there_is_no_stop_command(make_game, prefixes):
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineInstallation

    wine = WineInstallation(Path("/usr/bin/wine"), None, "9.0", None, "wine-9.0")
    manager = PrefixManager(prefixes, wine, runner=FakeWine(), registry_wait=0.2)

    plan = prepare_launch(make_game(exe="runnable"), wine=wine, prefixes=manager)

    assert plan.spec.stop_command is None


# --- Perfiles (sprint 4) -----------------------------------------------------------


def profile(**kwargs):
    defaults = {
        "id": "prueba",
        "name": "Prueba",
        "match": ProfileMatch(titles=("Juego de prueba",)),
    }
    return GameProfile(**{**defaults, **kwargs})


def test_matching_profile_is_applied(make_game, prefixes):
    game = make_game(exe="runnable")
    p = profile(
        arch="win32",
        environment={"LANG": "es_ES.UTF-8", "SDL_AUDIODRIVER": "pulse"},
        save_dirs=("%USERPROFILE%/Saved Games/Prueba", "%GAMEDIR%/Saves"),
        config_dirs=("%APPDATA%/Prueba",),
    )
    other = profile(id="otro", match=ProfileMatch(titles=("Otro",)), arch="win64")

    plan = prepare_launch(
        game,
        wine=WINE,
        prefixes=pm(prefixes, FakeWine()),
        profiles=[other, p],
        extra_env={"LANG": "C.UTF-8"},
    )

    assert plan.profile is p
    assert plan.prefix.arch == "win32"
    env = plan.spec.environment
    assert env["LANG"] == "C.UTF-8"  # extra_env manda sobre el perfil
    assert env["SDL_AUDIODRIVER"] == "pulse"
    assert env["WINEDEBUG"] == GAME_WINEDEBUG
    users = prefixes / "juego-de-prueba" / "drive_c" / "users"
    assert plan.save_dirs[0].parent.parent.parent == users
    assert plan.save_dirs[0].parts[-2:] == ("Saved Games", "Prueba")
    assert plan.save_dirs[1] == game.resolve() / "Saves"
    assert plan.config_dirs[0].parts[-3:] == ("AppData", "Roaming", "Prueba")


def test_explicit_arch_overrides_profile(make_game, prefixes):
    plan = prepare_launch(
        make_game(exe="runnable"),
        wine=WINE,
        prefixes=pm(prefixes, FakeWine()),
        profiles=[profile(arch="win32")],
        arch="win64",
    )
    assert plan.prefix.arch == "win64"


def test_without_matching_profile(make_game, prefixes):
    plan = prepare_launch(make_game(exe="runnable"), wine=WINE, prefixes=pm(prefixes, FakeWine()))

    assert plan.profile is None
    assert plan.save_dirs == ()
    assert plan.config_dirs == ()
    assert plan.spec.environment["WINEDEBUG"] == GAME_WINEDEBUG
