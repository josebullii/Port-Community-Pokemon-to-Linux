"""Ventana principal: navegación lateral y páginas (Biblioteca, Diagnóstico, Acerca de)."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from pokemon_to_linux import APP_NAME, __version__
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.ui.diagnostics_page import DiagnosticsPage
from pokemon_to_linux.ui.tasks import TaskRunner
from pokemon_to_linux.ui.widgets import page, wrapping_label

PAGE_TITLES = ("Biblioteca", "Diagnóstico", "Acerca de")


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths, log_file: str | None = None) -> None:
        super().__init__()
        self._paths = paths
        self._log_file = log_file
        self.tasks = TaskRunner(self)

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
        body = wrapping_label(
            "Todavía no has añadido ningún juego.\n\n"
            "Próximamente podrás seleccionar la carpeta de un fangame "
            "(p. ej. Pokémon Z) para analizarlo y ejecutarlo."
        )
        return page("Biblioteca", body)

    def _build_diagnostics_page(self) -> QWidget:
        self.diagnostics = DiagnosticsPage(self._paths, self._log_file, self.tasks)
        return page("Diagnóstico", self.diagnostics)

    def _build_about_page(self) -> QWidget:
        body = wrapping_label(
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
        return page("Acerca de", body)

    # --- Cierre ----------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API de Qt
        # Las tareas en marcha entregarían su resultado a widgets ya borrados.
        self.tasks.wait(5000)
        super().closeEvent(event)
