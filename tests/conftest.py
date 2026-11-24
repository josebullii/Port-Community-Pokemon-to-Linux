import logging
import os

import pytest

from pokemon_to_linux.infrastructure.logging.logger import ROOT_LOGGER_NAME

# Permite ejecutar las pruebas de Qt sin pantalla (CI, SSH, consola).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """QApplication compartida por todas las pruebas que usan widgets."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")  # noqa: N806
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_app_logger():
    """Cierra los handlers del logger de la app tras cada prueba (evita ficheros abiertos)."""
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def xdg_tmp(tmp_path, monkeypatch):
    """Redirige todas las rutas XDG a un directorio temporal."""
    for var, sub in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
    ):
        monkeypatch.setenv(var, str(tmp_path / sub))
    return tmp_path
