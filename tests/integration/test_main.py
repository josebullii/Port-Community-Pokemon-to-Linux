"""Prueba de humo del punto de entrada ``main()``."""

import sys

import pytest

from pokemon_to_linux import APP_ID
from pokemon_to_linux.infrastructure.logging.logger import LOG_FILE_NAME

pytestmark = pytest.mark.integration


@pytest.fixture
def no_event_loop(qapp, monkeypatch):
    """Hace que app.exec() vuelva al instante y guarda las ventanas mostradas."""
    from PySide6.QtWidgets import QApplication

    shown = []

    def fake_exec(*_args):
        shown.extend(w for w in QApplication.topLevelWidgets() if w.isVisible())
        return 0

    monkeypatch.setattr(QApplication, "exec", fake_exec)
    # main() instala un excepthook global: se restaura al terminar la prueba.
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    yield shown
    for widget in shown:
        widget.close()


def test_main_starts_shows_window_and_logs(xdg_tmp, no_event_loop):
    from pokemon_to_linux.main import main
    from pokemon_to_linux.ui.main_window import MainWindow

    exit_code = main([APP_ID])

    assert exit_code == 0
    assert any(isinstance(w, MainWindow) for w in no_event_loop)

    # Se crean las rutas XDG y el log de arranque/cierre.
    state_dir = xdg_tmp / "state" / APP_ID
    assert (xdg_tmp / "data" / APP_ID / "prefixes").is_dir()
    assert (xdg_tmp / "config" / APP_ID).is_dir()
    log = (state_dir / "logs" / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "Iniciando" in log
    assert "Aplicación cerrada (código 0)" in log


def test_qt_standard_texts_are_in_spanish(qapp):
    from PySide6.QtCore import QCoreApplication

    from pokemon_to_linux.main import install_qt_translations

    assert install_qt_translations(qapp)
    assert QCoreApplication.translate("QPlatformTheme", "&Yes") == "&Sí"
