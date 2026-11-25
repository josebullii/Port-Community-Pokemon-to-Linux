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


def test_cli_wine_probe(wine, xdg_tmp, capsys):
    from pokemon_to_linux.cli import main

    assert main(["wine", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "32 bits:     sí" in out


def test_cli_run_test_game(wine, qapp, xdg_tmp, make_game, capsys):
    """El juego de prueba lanzado desde la CLI devuelve su código de salida (7)."""
    from conftest import RUNNABLE_EXIT_CODE
    from pokemon_to_linux.cli import main

    assert main(["run", str(make_game(exe="runnable"))]) == RUNNABLE_EXIT_CODE
    out = capsys.readouterr().out
    assert "Fin: finished, código de salida 7" in out


def test_stop_game_closes_game_and_secondary_processes(
    qapp, wine, prefix_manager, make_game, tmp_path
):
    """Guía §5: gestionar el cierre del juego y de sus procesos secundarios.

    El "juego" es un programa Windows que espera 2 minutos. En el mismo
    prefijo se lanza aparte otro programa (como haría un juego con un
    proceso hijo). stop_game debe cerrar ambos mediante wineserver -k, antes
    de que actúe el cierre forzado.
    """
    import subprocess
    import time

    from pokemon_to_linux.application.launch_game import launch_game, prepare_launch, stop_game
    from pokemon_to_linux.infrastructure.wine.process_manager import (
        ProcessManager,
        ProcessState,
    )
    from pokemon_to_linux.infrastructure.wine.test_program import (
        build_exit_program,
        write_exit_program,
    )
    from pokemon_to_linux.infrastructure.wine.wine_manager import run_command

    long_ms = 120_000
    grace_ms = 15_000
    game = make_game(exe=None, extra={"Game.exe": build_exit_program(7, sleep_ms=long_ms)})
    plan = prepare_launch(game, wine=wine, prefixes=prefix_manager, game_id="prueba-parar")
    processes = ProcessManager(log_dir=tmp_path / "logs", stop_grace_ms=grace_ms)
    process = launch_game(plan, processes)

    child_exe = write_exit_program(plan.prefix.path / "drive_c" / "hijo.exe", 9, sleep_ms=long_ms)
    child = subprocess.Popen(
        [str(wine.wine), str(child_exe)],
        env=plan.spec.environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert not process.wait(3000), "el juego debería seguir en marcha"
        assert child.poll() is None, "el proceso secundario debería seguir en marcha"

        started = time.monotonic()
        stop_game(plan.game_id, processes)
        assert process.wait(60_000)
        elapsed = time.monotonic() - started

        assert process.outcome.state is ProcessState.STOPPED
        assert elapsed < grace_ms / 1000, f"lo cerró el cierre forzado ({elapsed:.1f} s)"
        assert child.wait(timeout=30) is not None  # el secundario también se cerró
        assert not processes.is_running(plan.game_id)
        # wineserver -w solo vuelve cuando no queda ningún proceso en el prefijo.
        assert run_command([str(wine.wineserver), "-w"], plan.spec.environment, 30).returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
        prefix_manager.delete(plan.game_id)
