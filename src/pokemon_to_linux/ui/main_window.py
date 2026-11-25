"""Ventana principal: navegación lateral y páginas (Biblioteca, Diagnóstico, Acerca de)."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from pokemon_to_linux import APP_NAME, __version__
from pokemon_to_linux.application.library import Library
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.infrastructure.database.connection import DatabaseError, open_database
from pokemon_to_linux.infrastructure.database.game_repository import GameRepository
from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.wine.process_manager import ProcessManager
from pokemon_to_linux.ui.diagnostics_page import DiagnosticsPage
from pokemon_to_linux.ui.library_page import LibraryPage, LibraryServices
from pokemon_to_linux.ui.tasks import TaskRunner
from pokemon_to_linux.ui.widgets import page, wrapping_label

log = get_logger(__name__)

PAGE_TITLES = ("Biblioteca", "Diagnóstico", "Acerca de")


class MainWindow(QMainWindow):
    def __init__(
        self,
        paths: AppPaths,
        log_file: str | None = None,
        *,
        services: LibraryServices | None = None,
    ) -> None:
        super().__init__()
        self._paths = paths
        self._log_file = log_file
        self._services = services
        self._database = None
        self.library: LibraryPage | None = None
        self.tasks = TaskRunner(self)

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1000, 680)

        self.nav = QListWidget()
        self.nav.addItems(PAGE_TITLES)
        self.nav.setFixedWidth(160)

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
        if self.library is not None:
            self.library.status_message.connect(self.statusBar().showMessage)

    # --- Páginas ---------------------------------------------------------

    def _build_library_page(self) -> QWidget:
        services = self._services
        if services is None:
            try:
                self._database = open_database(self._paths.database_path)
            except DatabaseError as exc:
                log.error("No se puede abrir la biblioteca: %s", exc)
                return page(
                    "Biblioteca",
                    wrapping_label(
                        f"No se puede abrir la biblioteca.\n\n{exc}\n\n"
                        f"Fichero: {self._paths.database_path}"
                    ),
                )
            services = LibraryServices.default(
                self._paths,
                Library(GameRepository(self._database)),
                ProcessManager(log_dir=self._paths.log_dir, parent=self),
            )
        self.library = LibraryPage(services, self.tasks)
        return self.library

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

    def confirm_close(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Hay un juego en marcha",
            "Si cierras Pokémon to Linux se cerrará también el juego, y lo que no "
            "hayas guardado se perderá. ¿Cerrar igualmente?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API de Qt
        if self.library is not None and self.library.running:
            if not self.confirm_close():
                event.ignore()
                return
            self.library.stop_all()
        # Las tareas en marcha entregarían su resultado a widgets ya borrados.
        self.tasks.wait(5000)
        if self._database is not None:
            self._database.close()
            self._database = None
        super().closeEvent(event)
