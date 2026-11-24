"""Pruebas con Wine real. Se omiten si Wine no está instalado.

Crear un prefijo tarda unos segundos; por eso se comparte uno win64 por módulo.
"""

import pytest

from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixError, PrefixManager
from pokemon_to_linux.infrastructure.wine.wine_manager import WineManager

pytestmark = pytest.mark.wine


@pytest.fixture(scope="module")
def wine():
    installation = WineManager().detect()
    if installation is None:
        pytest.skip("Wine no está instalado")
    return installation


@pytest.fixture(scope="module")
def prefix_manager(wine, tmp_path_factory):
    return PrefixManager(tmp_path_factory.mktemp("prefixes"), wine)


@pytest.fixture(scope="module")
def win64_prefix(prefix_manager):
    prefix = prefix_manager.create("prueba-win64", "win64")
    yield prefix
    prefix_manager.delete(prefix.game_id)


def test_wine_is_detected(wine):
    assert wine.version_tuple >= (6,)
    assert wine.wineserver is not None


def test_win64_prefix_is_created(win64_prefix):
    assert win64_prefix.arch == "win64"
    assert (win64_prefix.path / "drive_c" / "windows").is_dir()


def test_win64_prefix_runs_64_bit_programs(prefix_manager, win64_prefix):
    result = prefix_manager.run_test_program(win64_prefix, 64)
    assert result.ok, result.output


def test_win64_prefix_runs_32_bit_programs(prefix_manager, win64_prefix):
    """Necesario para Pokémon Z (i386). Requiere soporte de 32 bits (wine32 o WoW64)."""
    result = prefix_manager.run_test_program(win64_prefix, 32)
    assert result.ok, result.output


def test_ensure_reuses_the_prefix(prefix_manager, win64_prefix):
    assert prefix_manager.ensure(win64_prefix.game_id, "win64") == win64_prefix


def test_win32_prefix(prefix_manager):
    try:
        prefix = prefix_manager.create("prueba-win32", "win32")
    except PrefixError as exc:
        pytest.skip(f"Este Wine no admite prefijos win32: {exc}")
    try:
        assert prefix.arch == "win32"
        assert prefix_manager.run_test_program(prefix, 32).ok
        assert not prefix_manager.run_test_program(prefix, 64).ok
    finally:
        prefix_manager.delete(prefix.game_id)


def test_test_game_runs_end_to_end(qapp, wine, prefix_manager, make_game, tmp_path):
    """Entregable del sprint 3: un juego de prueba ejecutado desde Python.

    Juego RPG Maker XP falso cuyo Game.exe es un programa real de 32 bits
    (como Pokémon Z) que termina con código 7.
    """
    from conftest import RUNNABLE_EXIT_CODE
    from pokemon_to_linux.application.launch_game import launch_game, prepare_launch
    from pokemon_to_linux.infrastructure.wine.process_manager import (
        ProcessManager,
        ProcessState,
    )

    plan = prepare_launch(make_game(exe="runnable"), wine=wine, prefixes=prefix_manager)
    assert plan.test_result.ok  # el prefijo nuevo ejecuta 32 bits

    processes = ProcessManager(log_dir=tmp_path / "logs")
    process = launch_game(plan, processes)
    assert process.wait(120_000)

    outcome = process.outcome
    assert outcome.state is ProcessState.FINISHED, outcome
    assert outcome.exit_code == RUNNABLE_EXIT_CODE
    assert "código de salida 7" in outcome.log_file.read_text(encoding="utf-8")
    assert not processes.is_running(plan.game_id)
    prefix_manager.delete(plan.game_id)


def test_delete_removes_prefix(prefix_manager):
    prefix = prefix_manager.create("prueba-borrar", "win64")
    assert prefix_manager.delete(prefix.game_id) is True
    assert not prefix.path.exists()
