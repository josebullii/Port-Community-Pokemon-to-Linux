import os

import pytest

# Permite ejecutar las pruebas de Qt sin pantalla (CI, SSH, consola).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """QApplication compartida por todas las pruebas que usan widgets."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")  # noqa: N806
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
