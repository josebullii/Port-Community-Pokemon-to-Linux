"""Página Biblioteca de principio a fin, con Wine simulado.

El «Wine» es el intérprete de Python: al «lanzar» Game.exe, Python intenta
leerlo como un script y termina enseguida con código 1. Así se prueba el
flujo completo (tareas, prefijo, proceso, historial) sin Wine real.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import wait_until
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.domain.profile import parse_profile

pytestmark = pytest.mark.integration

PROFILE = parse_profile(
    {
        "schema": 1,
        "id": "prueba",
        "name": "Juego de prueba",
        "match": {"titles": ["Juego de prueba"]},
        "saves": {"paths": ["%USERPROFILE%/Saved Games/Prueba"]},
        "compatibility": {"status": "partial", "notes": "Solo para pruebas"},
        "known_issues": [
            {
                "id": "lento",
                "symptom": "Va lento",
                "solution": "Quita VSync",
                "output": ["SyntaxError"],
            }
        ],
    },
    "prueba.toml",
)


def fake_host(env=None, libraries=None):
    from pokemon_to_linux.infrastructure.system.host import HostSystem

    host = HostSystem(env={"DISPLAY": ":0"} if env is None else env, x11_socket_dir=None)
    host.__dict__["shared_libraries"] = {"libGL.so.1": {32, 64}} if libraries is None else libraries
    return host


class Dialogs:
    def __init__(self):
        self.answers = []
        self.asked = []
        self.informed = []
        self.opened = []
        self.folder = None


@pytest.fixture
def env(qapp, tmp_path):
    from conftest import FakeWine
    from pokemon_to_linux.application.library import Library
    from pokemon_to_linux.infrastructure.database.connection import open_database
    from pokemon_to_linux.infrastructure.database.game_repository import GameRepository
    from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixManager
    from pokemon_to_linux.infrastructure.wine.process_manager import ProcessManager
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineInstallation
    from pokemon_to_linux.ui.library_page import LibraryServices

    paths = AppPaths.from_environment(env={}, home=tmp_path / "home")
    conn = open_database(":memory:")
    state = {
        "wine": WineInstallation(Path(sys.executable), None, "9.0", None, "wine-9.0"),
        "host": fake_host(),
        "fake": FakeWine(),
    }
    services = LibraryServices(
        paths=paths,
        library=Library(GameRepository(conn)),
        processes=ProcessManager(log_dir=paths.log_dir),
        profiles=lambda: [PROFILE],
        detect_wine=lambda: state["wine"],
        host=lambda: state["host"],
        prefixes=lambda wine: PrefixManager(
            paths.prefixes_dir, wine, runner=state["fake"], registry_wait=0.2
        ),
    )
    state["services"] = services
    yield state
    services.processes.stop_all()
    conn.close()


@pytest.fixture
def page(env):
    from pokemon_to_linux.ui.library_page import LibraryPage
    from pokemon_to_linux.ui.tasks import TaskRunner

    tasks = TaskRunner()
    page = LibraryPage(env["services"], tasks)
    dialogs = Dialogs()
    page.choose_folder = lambda: dialogs.folder
    page.inform = lambda title, text: dialogs.informed.append((title, text))

    def ask(title, text):
        dialogs.asked.append((title, text))
        return dialogs.answers.pop(0)

    page.ask = ask
    page.open_path = dialogs.opened.append
    page.dialogs = dialogs
    messages = []
    page.status_message.connect(messages.append)
    page.messages = messages
    yield page
    tasks.wait()
    page.deleteLater()


def add(page, folder):
    page.dialogs.folder = folder
    page.add_game()
    wait_until(lambda: page.add_button.isEnabled())


def wait_for_details(page):
    wait_until(lambda: page.view.details is not None and page.view.activity == "idle")


def body(page):
    return page.view.body.text() + page.view.state.text() + page.view.summary.text()


# --- Añadir -------------------------------------------------------------------


def test_empty_library_explains_what_to_do(page):
    assert page.right.currentWidget() is page.empty
    assert "Añadir juego" in page.empty.text()


def test_add_game_and_show_details(page, make_game):
    folder = make_game(exe="mkxp-z")

    add(page, folder)
    wait_for_details(page)

    assert page.list.count() == 1
    assert page.selected_id() == "juego-de-prueba"
    assert page.right.currentWidget() is page.view
    text = body(page)
    assert "Juego de prueba" in page.view.title.text()
    assert "Parcial" in text
    assert "Solo para pruebas" in text
    assert "Listo para jugar" in text
    assert "OpenGL de 32 bits" in text
    assert "Va lento" in text
    assert "se crea la primera vez" in text
    assert page.view.play_button.isEnabled()
    assert not page.view.stop_button.isEnabled()
    assert not page.view.saves_button.isEnabled()  # aún no hay prefijo
    assert "Añadido: Juego de prueba" in page.messages


def test_add_unknown_folder_is_explained(page, tmp_path):
    add(page, tmp_path)

    [(title, text)] = page.dialogs.informed
    assert "No se reconoce el motor" in text
    assert page.list.count() == 0


def test_add_same_folder_twice(page, make_game):
    folder = make_game()
    add(page, folder)
    add(page, folder)

    [(_, text)] = page.dialogs.informed
    assert "ya está en la biblioteca" in text
    assert page.list.count() == 1


def test_cancelled_folder_dialog_does_nothing(page):
    page.dialogs.folder = None
    page.add_game()
    assert page.add_button.isEnabled()
    assert page.list.count() == 0


def test_html_in_the_title_is_not_interpreted(page, make_game):
    from conftest import build_game_ini

    add(page, make_game(ini=build_game_ini(title="<b>Negrita</b>")))
    wait_for_details(page)

    assert "&lt;b&gt;Negrita&lt;/b&gt;" in page.view.title.text()


# --- Jugar --------------------------------------------------------------------


def test_play_records_the_launch(page, env, make_game):
    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)

    page.view.play_button.click()
    library = env["services"].library
    wait_until(lambda: library.history("juego-de-prueba"), timeout=20)
    wait_for_details(page)

    [record] = library.history("juego-de-prueba")
    assert record.state == "finished"
    assert record.exit_code == 1
    assert record.log_file is not None and record.log_file.is_file()
    assert record.problems == ("lento",)  # «SyntaxError» en la salida de Python
    text = body(page)
    assert "Veces jugado:</b> 1" in text
    assert "terminó con el código 1" in text
    assert "Va lento" in text
    # El prefijo ya existe: se sabe dónde quedan las partidas.
    assert page.view.saves_button.isEnabled()
    assert "Saved Games" in text
    assert page.view.log_button.isEnabled()
    page.view.log_button.click()
    assert page.dialogs.opened == [record.log_file]


def test_play_asks_when_a_requirement_is_missing(page, env, make_game):
    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)
    env["host"] = fake_host(env={})  # sin sesión gráfica
    page.dialogs.answers = [False]

    page.view.play_button.click()
    wait_until(lambda: page.dialogs.asked)
    wait_until(lambda: page.view.activity == "idle")

    [(title, text)] = page.dialogs.asked
    assert "Sesión gráfica" in text
    assert "Lanzamiento cancelado" in page.messages
    assert env["services"].library.history("juego-de-prueba") == []
    assert env["fake"].calls == []  # ni siquiera se creó el prefijo


def test_play_without_wine_explains_how_to_install_it(page, env, make_game):
    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)
    env["wine"] = None

    page.view.play_button.click()
    wait_until(lambda: page.dialogs.informed)

    [(_, text)] = page.dialogs.informed
    assert "Wine no está instalado" in text
    assert page.view.activity == "idle"
    assert page.view.play_button.isEnabled()


def test_play_when_wine_cannot_run_32_bit(page, env, make_game):
    from conftest import FakeWine

    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)
    env["fake"] = FakeWine(program_code=1)

    page.view.play_button.click()
    wait_until(lambda: page.dialogs.informed, timeout=20)

    [(_, text)] = page.dialogs.informed
    assert "no puede ejecutar programas de 32 bits" in text
    assert "wine32:i386" in text


def test_stop_a_running_game(page, env, make_game, monkeypatch):
    from pokemon_to_linux.application import launch_game as real

    def long_running(plan, processes):
        spec = plan.spec.__class__(
            plan.spec.game_id,
            Path(sys.executable),
            ("-c", "import time; time.sleep(60)"),
            plan.spec.working_dir,
        )
        return processes.launch(spec)

    monkeypatch.setattr("pokemon_to_linux.ui.library_page.launch_game", long_running)
    assert real.launch_game is not long_running
    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)

    page.view.play_button.click()
    wait_until(lambda: page.view.activity == "running", timeout=20)
    assert page.running == ("juego-de-prueba",)
    assert page.view.stop_button.isEnabled()
    assert not page.view.play_button.isEnabled()
    assert not page.view.remove_button.isEnabled()

    page.view.stop_button.click()
    library = env["services"].library
    wait_until(lambda: library.history("juego-de-prueba"), timeout=20)

    assert library.history("juego-de-prueba")[0].state == "stopped"
    assert page.running == ()


# --- Quitar y abrir carpetas --------------------------------------------------


def test_remove_asks_first_and_keeps_files(page, env, make_game):
    folder = make_game()
    add(page, folder)
    wait_for_details(page)

    page.dialogs.answers = [False]
    page.view.remove_button.click()
    assert page.list.count() == 1

    page.dialogs.answers = [True]
    page.view.remove_button.click()
    assert page.list.count() == 0
    assert page.right.currentWidget() is page.empty
    assert "no se borra nada" in page.dialogs.asked[0][1].lower()
    assert (folder / "Game.exe").is_file()


def test_open_game_folder(page, make_game):
    folder = make_game()
    add(page, folder)
    wait_for_details(page)

    page.view.folder_button.click()

    assert page.dialogs.opened == [folder.resolve()]


def test_open_saves_folder_goes_to_the_nearest_existing_folder(page, env, make_game):
    folder = make_game(exe="mkxp-z")
    add(page, folder)
    prefix = env["services"].paths.prefixes_dir / "juego-de-prueba"
    (prefix / "drive_c" / "users" / "jose").mkdir(parents=True)
    (prefix / "system.reg").write_text("WINE REGISTRY Version 2\n#arch=win64\n")
    page.inspect("juego-de-prueba")
    wait_for_details(page)

    page.view.saves_button.click()

    # Saved Games/Prueba aún no existe (no se ha guardado ninguna partida).
    assert page.dialogs.opened == [prefix / "drive_c" / "users" / "jose"]


def test_history_from_previous_sessions_is_shown(page, env, make_game):
    from pokemon_to_linux.infrastructure.wine.process_manager import (
        LaunchOutcome,
        ProcessState,
    )

    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)
    library = env["services"].library
    library.record_launch(
        "juego-de-prueba",
        LaunchOutcome("juego-de-prueba", ProcessState.CRASHED, None, 3600, "se cerró"),
    )

    page.reload()
    text = body(page)

    assert "1 h 00 min" in text
    assert "se cerró de forma inesperada (se cerró)" in text
    assert datetime.now(UTC).astimezone().strftime("%d/%m/%Y") in text


# --- Ventana ------------------------------------------------------------------


def test_main_window_asks_before_closing_with_a_game_running(env, qapp, tmp_path, monkeypatch):
    from pokemon_to_linux.ui.main_window import MainWindow

    window = MainWindow(env["services"].paths, services=env["services"])
    monkeypatch.setattr(type(window.library), "busy", property(lambda self: ("x",)))
    answers = [False]
    window.confirm_close = lambda: answers.pop(0)
    stopped = []
    window.library.shutdown = lambda: stopped.append(True)

    assert window.close() is False
    assert stopped == []
    window.confirm_close = lambda: True
    assert window.close() is True
    assert stopped == [True]
    window.deleteLater()


def test_format_duration():
    from pokemon_to_linux.ui.game_details import format_duration

    assert format_duration(0) == "—"
    assert format_duration(30) == "menos de 1 min"
    assert format_duration(125) == "2 min"
    assert format_duration(3 * 3600 + 5 * 60) == "3 h 05 min"


def test_closing_while_preparing_does_not_launch_the_game(page, env, make_game, monkeypatch):
    """Si la ventana se cierra mientras se crea el prefijo, el juego no debe arrancar después."""
    import threading

    from pokemon_to_linux.application import launch_game as real

    release = threading.Event()

    def slow_prepare(*args, **kwargs):
        release.wait(10)
        return real.prepare_launch(*args, **kwargs)

    monkeypatch.setattr("pokemon_to_linux.ui.library_page.prepare_launch", slow_prepare)
    add(page, make_game(exe="mkxp-z"))
    wait_for_details(page)

    page.view.play_button.click()
    wait_until(lambda: page.view.activity == "preparing")
    assert page.busy == ("juego-de-prueba",)

    page.shutdown()
    release.set()
    wait_until(lambda: page.tasks.pending == 0, timeout=20)

    assert env["services"].processes.active() == ()
    assert page.running == ()
    assert env["services"].library.history("juego-de-prueba") == []
