import pytest

from pokemon_to_linux import APP_NAME
from pokemon_to_linux.config import AppPaths

pytestmark = pytest.mark.integration


@pytest.fixture
def window(qapp, tmp_path):
    from pokemon_to_linux.ui.main_window import MainWindow

    paths = AppPaths.from_environment(env={}, home=tmp_path)
    win = MainWindow(paths, log_file=str(tmp_path / "app.log"))
    yield win
    win.close()
    win.deleteLater()


def test_window_title_contains_app_name(window):
    assert APP_NAME in window.windowTitle()


def test_navigation_has_one_page_per_entry(window):
    assert window.nav.count() == window.pages.count() == 3
    assert window.pages.currentIndex() == 0


def test_navigation_switches_pages(window):
    window.nav.setCurrentRow(2)
    assert window.pages.currentIndex() == 2

    window.nav.setCurrentRow(1)
    assert window.pages.currentIndex() == 1


def test_window_shows_without_errors(window, qapp):
    window.show()
    qapp.processEvents()
    assert window.isVisible()


def _diagnostics_text(window):
    from PySide6.QtWidgets import QLabel

    page = window.pages.widget(1)
    return " ".join(label.text() for label in page.findChildren(QLabel))


def test_diagnostics_shows_wine_not_installed(qapp, tmp_path, monkeypatch):
    from pokemon_to_linux.ui.main_window import MainWindow

    monkeypatch.setattr("pokemon_to_linux.ui.main_window.WineManager.detect", lambda self: None)
    win = MainWindow(AppPaths.from_environment(env={}, home=tmp_path))

    assert "no instalado" in _diagnostics_text(win)
    win.deleteLater()


def test_diagnostics_shows_wine_version(qapp, tmp_path, monkeypatch):
    from pathlib import Path

    from pokemon_to_linux.infrastructure.wine.wine_manager import WineInstallation
    from pokemon_to_linux.ui.main_window import MainWindow

    wine = WineInstallation(Path("/usr/bin/wine"), None, "9.0", None, "wine-9.0 (Ubuntu)")
    monkeypatch.setattr("pokemon_to_linux.ui.main_window.WineManager.detect", lambda self: wine)
    win = MainWindow(AppPaths.from_environment(env={}, home=tmp_path))

    assert "wine-9.0 (Ubuntu)" in _diagnostics_text(win)
    win.deleteLater()


def test_diagnostics_shows_wine_error(qapp, tmp_path, monkeypatch):
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineError
    from pokemon_to_linux.ui.main_window import MainWindow

    def broken(self):
        raise WineError("wine --version falló")

    monkeypatch.setattr("pokemon_to_linux.ui.main_window.WineManager.detect", broken)
    win = MainWindow(AppPaths.from_environment(env={}, home=tmp_path))

    assert "error: wine --version falló" in _diagnostics_text(win)
    win.deleteLater()


def _host_with(libraries):
    from pokemon_to_linux.infrastructure.system.host import HostSystem

    host = HostSystem(env={})
    host.__dict__["shared_libraries"] = libraries
    return host


@pytest.mark.parametrize(
    ("libraries", "expected"),
    [
        (
            {"libGL.so.1": {32, 64}, "libGLX.so.0": {32, 64}, "libGLX_mesa.so.0": {32, 64}},
            "OpenGL de 32 bits: sí (libGL.so.1 (mesa))",
        ),
        ({"libGL.so.1": {64}}, "OpenGL de 32 bits: NO. Instala OpenGL de 32 bits"),
        (None, "OpenGL de 32 bits: no se sabe"),
    ],
)
def test_diagnostics_shows_opengl(qapp, tmp_path, monkeypatch, libraries, expected):
    from pokemon_to_linux.ui.main_window import MainWindow

    monkeypatch.setattr(
        "pokemon_to_linux.application.check_requirements.HostSystem",
        lambda: _host_with(libraries),
    )
    win = MainWindow(AppPaths.from_environment(env={}, home=tmp_path))

    text = _diagnostics_text(win)
    assert expected in text
    assert "OpenGL de 64 bits" in text
    win.deleteLater()
