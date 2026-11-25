"""Punto de entrada de la aplicación."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from pokemon_to_linux import APP_ID, APP_NAME, __version__
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.infrastructure.logging.logger import (
    get_logger,
    install_excepthook,
    setup_logging,
)


def install_qt_translations(app) -> bool:
    """Textos de Qt en español («Sí», «No», «Cancelar», el diálogo de carpetas…).

    La interfaz está en español: sin esto, los botones estándar salen en inglés.
    """
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(QLocale(QLocale.Language.Spanish), "qtbase", "_", folder):
        get_logger(__name__).info("No hay traducción de Qt al español en %s", folder)
        return False
    app.installTranslator(translator)
    return True


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    paths = AppPaths.from_environment()
    paths.ensure()
    log_file = setup_logging(paths.log_dir)
    install_excepthook()

    log = get_logger(__name__)
    log.info("Iniciando %s %s", APP_NAME, __version__)

    # Import tardío: así config y logging se pueden usar sin Qt.
    from PySide6.QtWidgets import QApplication

    from pokemon_to_linux.ui.main_window import MainWindow

    # Reutiliza la instancia si ya existe (Qt solo admite una por proceso).
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    install_qt_translations(app)

    window = MainWindow(paths, log_file=str(log_file))
    window.show()

    exit_code = app.exec()
    log.info("Aplicación cerrada (código %s)", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
