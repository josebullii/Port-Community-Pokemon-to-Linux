"""Ventana principal: navegación lateral y páginas (Biblioteca, Diagnóstico, Acerca de)."""

from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pokemon_to_linux import APP_NAME, __version__
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.infrastructure.wine.wine_manager import WineError, WineManager


def wine_status() -> str:
    """Texto para la página de diagnóstico (``wine --version`` tarda milisegundos)."""
    try:
        wine = WineManager().detect()
    except WineError as exc:
        return f"error: {exc}"
    if wine is None:
        return "no instalado (instálalo desde los repositorios de tu distribución)"
    return f"{wine.description} ({wine.wine})"


PAGE_TITLES = ("Biblioteca", "Diagnóstico", "Acerca de")


def _wrapping_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _page(title: str, body: QWidget) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    heading = QLabel(f"<h2>{title}</h2>")
    layout.addWidget(heading)
    layout.addWidget(body)
    layout.addStretch(1)
    return page


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, log_file: str | None = None) -> None:
        super().__init__()
        self._paths = paths
        self._log_file = log_file

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(900, 600)

        self.nav = QListWidget()
        self.nav.addItems(PAGE_TITLES)
        self.nav.setFixedWidth(180)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_library_page())
        self.pages.addWidget(self._build_diagnostics_page())
        self.pages.addWidget(self._build_about_page())

        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Listo")

    # --- Páginas ---------------------------------------------------------

    def _build_library_page(self) -> QWidget:
        body = _wrapping_label(
            "Todavía no has añadido ningún juego.\n\n"
            "Próximamente podrás seleccionar la carpeta de un fangame "
            "(p. ej. Pokémon Z) para analizarlo y ejecutarlo."
        )
        return _page("Biblioteca", body)

    def _build_diagnostics_page(self) -> QWidget:
        body = QWidget()
        form = QFormLayout(body)
        rows = {
            "Versión": __version__,
            "Python": sys.version.split()[0],
            "PySide6 / Qt": f"{pyside_version} / {qVersion()}",
            "Sistema": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "Datos": str(self._paths.data_dir),
            "Configuración": str(self._paths.config_dir),
            "Caché": str(self._paths.cache_dir),
            "Estado": str(self._paths.state_dir),
            "Log": self._log_file or "(sin fichero)",
            "Wine": wine_status(),
        }
        for key, value in rows.items():
            form.addRow(f"{key}:", _wrapping_label(value))
        return _page("Diagnóstico", body)

    def _build_about_page(self) -> QWidget:
        body = _wrapping_label(
            f"{APP_NAME} {__version__}\n\n"
            "Lanzador y gestor de compatibilidad para fangames de Pokémon creados "
            "con RPG Maker XP.\n\n"
            "Licencia: GNU GPL v3 o posterior (GPL-3.0-or-later). "
            "Se distribuye SIN NINGUNA GARANTÍA.\n\n"
            "Este proyecto no incluye ni distribuye juegos, ROMs, DLL ni runtimes "
            "propietarios. Pokémon es una marca de Nintendo, Game Freak y The Pokémon "
            "Company; este proyecto no está afiliado a ellas. Cada fangame pertenece "
            "a sus autores."
        )
        return _page("Acerca de", body)
