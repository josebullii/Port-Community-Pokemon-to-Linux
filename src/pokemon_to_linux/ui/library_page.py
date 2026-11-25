"""Página «Biblioteca»: añadir juegos, ver sus detalles y jugar sin abrir una terminal.

Flujo de «Jugar» (el mismo que ``pokemon-to-linux-cli run``):

1. En segundo plano: detectar Wine, analizar la carpeta y comprobar los
   requisitos. Si falta algo imprescindible, se pregunta antes de seguir.
2. En segundo plano: ``prepare_launch`` (crea el prefijo la primera vez y
   prueba que Wine ejecuta los bits del juego).
3. En el hilo principal: lanzar el proceso y reconocer problemas conocidos
   en su salida. Al terminar, se guarda en el historial.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pokemon_to_linux.application.analyze_game import GameAnalysis, analyze_game
from pokemon_to_linux.application.check_requirements import check_requirements
from pokemon_to_linux.application.diagnose_output import OutputDiagnoser
from pokemon_to_linux.application.launch_game import (
    NO_WINE_MESSAGE,
    LaunchPlan,
    launch_game,
    prepare_launch,
)
from pokemon_to_linux.application.library import GameDetails, Library, LibraryError, inspect_game
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.domain.game import Game
from pokemon_to_linux.domain.profile import GameProfile
from pokemon_to_linux.domain.requirements import RequirementCheck
from pokemon_to_linux.infrastructure.filesystem.profile_store import load_profiles
from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.system.host import HostSystem
from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixManager
from pokemon_to_linux.infrastructure.wine.process_manager import (
    GameProcess,
    LaunchOutcome,
    ProcessError,
    ProcessManager,
)
from pokemon_to_linux.infrastructure.wine.wine_manager import WineInstallation, WineManager
from pokemon_to_linux.ui.game_details import Activity, GameDetailsView, describe_launch
from pokemon_to_linux.ui.tasks import TaskRunner
from pokemon_to_linux.ui.widgets import wrapping_label

log = get_logger(__name__)

ID_ROLE = Qt.ItemDataRole.UserRole

EMPTY_TEXT = (
    "Todavía no has añadido ningún juego.\n\n"
    "Pulsa «Añadir juego…» y elige la carpeta del juego: la que contiene Game.exe, "
    "Game.ini y la carpeta Data (p. ej. «POKEMON Z V2.19»).\n\n"
    "Pokémon to Linux no copia ni modifica el juego: lo deja donde está."
)


def _load_profiles(paths: AppPaths) -> Sequence[GameProfile]:
    profiles = load_profiles(paths.profiles_dir)
    for error in profiles.errors:
        log.warning("Perfil ignorado: %s", error)
    return profiles.profiles


@dataclass
class LibraryServices:
    """Lo que la página necesita del resto de la aplicación (sustituible en las pruebas)."""

    paths: AppPaths
    library: Library
    processes: ProcessManager
    profiles: Callable[[], Sequence[GameProfile]]
    detect_wine: Callable[[], WineInstallation | None]
    host: Callable[[], HostSystem]
    prefixes: Callable[[WineInstallation], PrefixManager]

    @classmethod
    def default(cls, paths: AppPaths, library: Library, processes: ProcessManager):
        return cls(
            paths=paths,
            library=library,
            processes=processes,
            profiles=lambda: _load_profiles(paths),
            detect_wine=lambda: WineManager().detect(),
            host=HostSystem,
            prefixes=lambda wine: PrefixManager(paths.prefixes_dir, wine),
        )


@dataclass(frozen=True, slots=True)
class _PreLaunch:
    wine: WineInstallation
    analysis: GameAnalysis
    checks: tuple[RequirementCheck, ...]
    profiles: Sequence[GameProfile]


class LibraryPage(QWidget):
    status_message = Signal(str)
    """Texto para la barra de estado de la ventana."""

    def __init__(self, services: LibraryServices, tasks: TaskRunner, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.tasks = tasks
        self._details: dict[str, GameDetails] = {}
        self._activity: dict[str, Activity] = {}
        self._running: dict[str, GameProcess] = {}
        self._diagnosers: dict[str, OutputDiagnoser] = {}
        self._inspections: dict[str, int] = {}
        """Última comprobación pedida por juego: las anteriores se descartan al llegar."""

        self.add_button = QPushButton("Añadir juego…")
        self.add_button.clicked.connect(self.add_game)
        self.list = QListWidget()
        self.list.setMinimumWidth(200)
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.add_button)
        left_layout.addWidget(self.list)

        self.view = GameDetailsView()
        self.view.play_requested.connect(self.play)
        self.view.stop_requested.connect(self.stop)
        self.view.recheck_requested.connect(self.inspect)
        self.view.open_saves_requested.connect(self._open_saves)
        self.view.open_folder_requested.connect(self._open_game_folder)
        self.view.open_log_requested.connect(self._open_log)
        self.view.remove_requested.connect(self.remove_game)

        self.empty = wrapping_label(EMPTY_TEXT)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.right = QStackedWidget()
        self.right.addWidget(self.empty)
        self.right.addWidget(self.view)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 600])

        heading = QLabel("<h2>Biblioteca</h2>")
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        row = QHBoxLayout()
        row.addWidget(splitter)
        layout.addLayout(row, 1)

        self.services.processes.finished.connect(self._on_finished)
        self.reload()

    # --- Diálogos (se sustituyen en las pruebas) ------------------------------

    def choose_folder(self) -> Path | None:
        folder = QFileDialog.getExistingDirectory(
            self, "Elige la carpeta del juego (la que tiene Game.exe)", str(Path.home())
        )
        return Path(folder) if folder else None

    def ask(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text)
        return answer == QMessageBox.StandardButton.Yes

    def inform(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def open_path(self, path: Path) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.inform("No se puede abrir", f"No se ha podido abrir {path}.")

    # --- Lista ----------------------------------------------------------------

    def reload(self, select: str | None = None) -> None:
        current = select or self.selected_id()
        self.list.blockSignals(True)
        self.list.clear()
        for game in self.services.library.games():
            item = QListWidgetItem(game.name)
            item.setData(ID_ROLE, game.id)
            item.setToolTip(str(game.path))
            self.list.addItem(item)
            if game.id == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._show_selected()

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(ID_ROLE) if item is not None else None

    def _show_selected(self) -> None:
        game_id = self.selected_id()
        game = self.services.library.get(game_id) if game_id else None
        if game is None:
            self.right.setCurrentWidget(self.empty)
            return
        self.right.setCurrentWidget(self.view)
        self._refresh_view(game)
        if game.id not in self._details and self._activity.get(game.id) is None:
            self.inspect(game.id)

    def _refresh_view(self, game: Game | None = None) -> None:
        game = game or (self.services.library.get(gid) if (gid := self.selected_id()) else None)
        if game is None:
            return
        self.view.show_game(
            game,
            self.services.library.history(game.id),
            self._details.get(game.id),
            self._activity.get(game.id, Activity.IDLE),
        )

    def _set_activity(self, game_id: str, activity: Activity) -> None:
        if activity is Activity.IDLE:
            self._activity.pop(game_id, None)
        else:
            self._activity[game_id] = activity
        if game_id == self.selected_id():
            self.view.set_activity(activity)

    # --- Añadir y quitar ------------------------------------------------------

    def add_game(self) -> None:
        folder = self.choose_folder()
        if folder is None:
            return
        self.add_button.setEnabled(False)
        self.status_message.emit(f"Analizando {folder}…")

        def done(analysis: GameAnalysis) -> None:
            self.add_button.setEnabled(True)
            try:
                game = self.services.library.add(analysis)
            except LibraryError as exc:
                self.status_message.emit("No se ha añadido el juego")
                self.inform("No se puede añadir el juego", str(exc))
                return
            self.status_message.emit(f"Añadido: {game.name}")
            self.reload(select=game.id)

        def failed(exc: object) -> None:
            self.add_button.setEnabled(True)
            self.status_message.emit("No se ha añadido el juego")
            self.inform("No se puede añadir el juego", f"No se puede leer {folder}: {exc}")

        self.tasks.run(lambda: analyze_game(folder), done, failed, name="análisis del juego")

    def remove_game(self, game_id: str) -> None:
        game = self.services.library.get(game_id)
        if game is None or self._activity.get(game_id):
            return
        if not self.ask(
            "Quitar de la biblioteca",
            f"¿Quitar «{game.name}» de la biblioteca?\n\n"
            "No se borra nada del disco: la carpeta del juego y su prefijo de Wine (con "
            "las partidas guardadas) se quedan donde están. Si lo vuelves a añadir, "
            "recuperarás las partidas.",
        ):
            return
        self.services.library.remove(game_id)
        self._details.pop(game_id, None)
        self.status_message.emit(f"Quitado de la biblioteca: {game.name}")
        self.reload()

    # --- Detalles -------------------------------------------------------------

    def inspect(self, game_id: str) -> None:
        game = self.services.library.get(game_id)
        if game is None or self._activity.get(game_id) not in (None, Activity.CHECKING):
            return
        token = self._inspections.get(game_id, 0) + 1
        self._inspections[game_id] = token
        self._details.pop(game_id, None)
        self._set_activity(game_id, Activity.CHECKING)
        self._refresh_view()
        services = self.services

        def work() -> GameDetails:
            return inspect_game(
                game,
                profiles=services.profiles(),
                prefixes_dir=services.paths.prefixes_dir,
                host=services.host(),
            )

        def done(details: GameDetails) -> None:
            if self._inspections.get(game_id) != token:
                return  # hay una comprobación más reciente en marcha
            self._details[game_id] = details
            self._set_activity(game_id, Activity.IDLE)
            self._refresh_view()

        def failed(exc: object) -> None:
            done(GameDetails(game, None, f"Error inesperado: {exc}"))

        self.tasks.run(work, done, failed, name="comprobación del juego")

    # --- Jugar ----------------------------------------------------------------

    def play(self, game_id: str) -> None:
        game = self.services.library.get(game_id)
        if game is None or self._activity.get(game_id):
            return
        self._set_activity(game_id, Activity.CHECKING)
        self.status_message.emit(f"Comprobando {game.name}…")
        services = self.services

        def work() -> _PreLaunch:
            wine = services.detect_wine()
            if wine is None:
                raise LibraryError(NO_WINE_MESSAGE)
            analysis = analyze_game(game.path)
            if not analysis.detection.detected:
                raise LibraryError(
                    "La carpeta ya no contiene un juego reconocible. ¿Se ha movido o borrado?"
                )
            checks = check_requirements(analysis, services.host())
            return _PreLaunch(wine, analysis, checks, services.profiles())

        self.tasks.run(
            work,
            lambda pre: self._confirm_and_prepare(game, pre),
            lambda exc: self._launch_failed(game, exc),
            name="comprobación antes de jugar",
        )

    def _confirm_and_prepare(self, game: Game, pre: _PreLaunch) -> None:
        blocking = [c for c in pre.checks if c.blocking]
        if blocking:
            problems = "\n\n".join(f"✖ {c.label}: {c.detail}\n→ {c.hint}" for c in blocking)
            if not self.ask(
                "Falta algo para jugar",
                f"{problems}\n\nSin esto, lo más probable es que el juego no funcione. "
                "¿Lanzarlo igualmente?",
            ):
                self._set_activity(game.id, Activity.IDLE)
                self.status_message.emit("Lanzamiento cancelado")
                return
        self._set_activity(game.id, Activity.PREPARING)
        self.status_message.emit(f"Preparando {game.name}…")
        services = self.services

        def work() -> LaunchPlan:
            return prepare_launch(
                game.path,
                wine=pre.wine,
                prefixes=services.prefixes(pre.wine),
                game_id=game.id,
                profiles=pre.profiles,
                analysis=pre.analysis,
            )

        self.tasks.run(
            work,
            lambda plan: self._start(game, plan),
            lambda exc: self._launch_failed(game, exc),
            name="preparación del juego",
        )

    def _start(self, game: Game, plan: LaunchPlan) -> None:
        try:
            process = launch_game(plan, self.services.processes)
        except ProcessError as exc:
            self._launch_failed(game, exc)
            return
        diagnoser = OutputDiagnoser(plan.profile)
        process.output.connect(diagnoser.feed)
        self._running[game.id] = process
        self._diagnosers[game.id] = diagnoser
        self._set_activity(game.id, Activity.RUNNING)
        self.status_message.emit(f"Jugando a {game.name}")
        # Con el prefijo recién creado ya se conocen las carpetas de partidas.
        if plan.prefix_created:
            self._details.pop(game.id, None)

    def _launch_failed(self, game: Game, exc: object) -> None:
        self._set_activity(game.id, Activity.IDLE)
        self.status_message.emit(f"No se ha podido lanzar {game.name}")
        self.inform(f"No se puede jugar a {game.name}", str(exc))

    def stop(self, game_id: str) -> None:
        if game_id in self._running:
            self._set_activity(game_id, Activity.STOPPING)
            self.services.processes.stop(game_id)

    def _on_finished(self, outcome: LaunchOutcome) -> None:
        game_id = outcome.game_id
        self._running.pop(game_id, None)
        diagnoser = self._diagnosers.pop(game_id, None)
        problems = diagnoser.problems if diagnoser else ()
        game = self.services.library.get(game_id)
        self._set_activity(game_id, Activity.IDLE)
        if game is None:
            return
        record = self.services.library.record_launch(game_id, outcome, problems)
        self.status_message.emit(f"{game.name}: {describe_launch(record)}")
        if game_id == self.selected_id():
            if game_id in self._details:
                self._refresh_view()
            else:
                self.inspect(game_id)

    @property
    def running(self) -> tuple[str, ...]:
        return tuple(self._running)

    def stop_all(self, timeout_ms: int = 10_000) -> None:
        """Detiene los juegos en marcha y espera a que terminen (al cerrar la ventana)."""
        for game_id, process in list(self._running.items()):
            self.services.processes.stop(game_id)
            process.wait(timeout_ms)

    # --- Carpetas y logs ------------------------------------------------------

    def _open_saves(self, game_id: str) -> None:
        details = self._details.get(game_id)
        if details is None or not details.save_dirs:
            return
        folder = details.save_dirs[0]
        # Antes de la primera partida guardada la carpeta aún no existe.
        while not folder.exists() and folder != details.prefix_path:
            folder = folder.parent
        self.open_path(folder)

    def _open_game_folder(self, game_id: str) -> None:
        if (game := self.services.library.get(game_id)) is not None:
            self.open_path(game.path)

    def _open_log(self, game_id: str) -> None:
        if game_id == self.selected_id() and (log_file := self.view.latest_log()):
            self.open_path(log_file)
