"""Vista de detalles de un juego: estado, requisitos, partidas, historial y acciones.

Todo el texto que viene del juego o del sistema (títulos, rutas, salida de
Wine) se escapa antes de mostrarse como HTML.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pokemon_to_linux.application.analyze_game import engine_display_name
from pokemon_to_linux.application.diagnose_output import find_issue
from pokemon_to_linux.application.library import GameDetails
from pokemon_to_linux.domain.game import Game, LaunchRecord
from pokemon_to_linux.domain.requirements import CheckStatus
from pokemon_to_linux.ui.widgets import wrapping_label

CHECK_MARKS = {
    CheckStatus.OK: "✔",
    CheckStatus.WARNING: "⚠",
    CheckStatus.ERROR: "✖",
    CheckStatus.UNKNOWN: "?",
}

STATUS_COLORS = {
    "not_tested": "#777777",
    "not_working": "#c62828",
    "partial": "#ef6c00",
    "compatible": "#2e7d32",
}


class Activity(StrEnum):
    """Qué está pasando con el juego seleccionado."""

    IDLE = "idle"
    CHECKING = "checking"
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPING = "stopping"


ACTIVITY_TEXT = {
    Activity.CHECKING: "Comprobando requisitos…",
    Activity.PREPARING: "Preparando el juego (la primera vez se crea su prefijo de Wine; "
    "tarda unos segundos)…",
    Activity.RUNNING: "En marcha",
    Activity.STOPPING: "Deteniendo…",
}


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "menos de 1 min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def format_moment(moment: datetime | None) -> str:
    return moment.astimezone().strftime("%d/%m/%Y %H:%M") if moment else "nunca"


def describe_launch(record: LaunchRecord) -> str:
    match record.state:
        case "finished" if record.exit_code == 0:
            text = "terminó bien"
        case "finished":
            text = f"terminó con el código {record.exit_code}"
        case "crashed":
            text = "se cerró de forma inesperada"
        case "stopped":
            text = "detenido desde la aplicación"
        case "failed":
            text = "no llegó a arrancar"
        case _:
            text = record.state
    if record.error and record.state in ("crashed", "failed"):
        text += f" ({record.error})"
    return text


def _section(title: str, body_html: str) -> str:
    return f"<h3 style='margin-bottom:2px'>{escape(title)}</h3>{body_html}"


def _paragraphs(lines: Sequence[str]) -> str:
    return "".join(f"<p style='margin:2px 0'>{line}</p>" for line in lines)


class GameDetailsView(QWidget):
    """Muestra un juego. Las acciones se piden con señales (con el id del juego)."""

    play_requested = Signal(str)
    stop_requested = Signal(str)
    recheck_requested = Signal(str)
    open_saves_requested = Signal(str)
    open_folder_requested = Signal(str)
    open_log_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.game: Game | None = None
        self.details: GameDetails | None = None
        self.history: Sequence[LaunchRecord] = ()
        self.activity = Activity.IDLE

        self.title = wrapping_label(rich=True)
        self.summary = wrapping_label(rich=True)
        self.state = wrapping_label(rich=True)
        self.body = wrapping_label(rich=True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.body.setOpenExternalLinks(False)

        self.play_button = QPushButton("Jugar")
        self.play_button.setDefault(True)
        self.stop_button = QPushButton("Detener")
        self.recheck_button = QPushButton("Volver a comprobar")
        self.saves_button = QPushButton("Abrir carpeta de partidas")
        self.folder_button = QPushButton("Abrir carpeta del juego")
        self.log_button = QPushButton("Ver último log")
        self.remove_button = QPushButton("Quitar de la biblioteca")

        for button, signal in (
            (self.play_button, self.play_requested),
            (self.stop_button, self.stop_requested),
            (self.recheck_button, self.recheck_requested),
            (self.saves_button, self.open_saves_requested),
            (self.folder_button, self.open_folder_requested),
            (self.log_button, self.open_log_requested),
            (self.remove_button, self.remove_requested),
        ):
            button.clicked.connect(lambda _=False, s=signal: self._emit(s))

        buttons = QGridLayout()
        buttons.addWidget(self.play_button, 0, 0)
        buttons.addWidget(self.stop_button, 0, 1)
        buttons.addWidget(self.recheck_button, 0, 2)
        buttons.addWidget(self.saves_button, 1, 0)
        buttons.addWidget(self.folder_button, 1, 1)
        buttons.addWidget(self.log_button, 1, 2)
        buttons.addWidget(self.remove_button, 2, 2)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self.title)
        layout.addWidget(self.summary)
        layout.addWidget(self.state)
        layout.addLayout(buttons)
        layout.addWidget(self.body)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _emit(self, signal: Signal) -> None:
        if self.game is not None:
            signal.emit(self.game.id)

    # --- Contenido ----------------------------------------------------------

    def show_game(
        self,
        game: Game,
        history: Sequence[LaunchRecord],
        details: GameDetails | None,
        activity: Activity,
    ) -> None:
        self.game, self.history, self.details, self.activity = game, history, details, activity
        self.title.setText(f"<h2>{escape(game.name)}</h2>")
        about = [engine_display_name(game.engine or ""), game.runtime or "runtime desconocido"]
        if game.bits:
            about.append(f"{game.bits} bits")
        lines = [
            f"<b>Carpeta:</b> {escape(str(game.path))}",
            f"<b>Motor:</b> {escape(', '.join(about))}",
        ]
        if details is not None and details.profile is not None:
            profile = details.profile
            color = STATUS_COLORS.get(profile.status.value, "#777777")
            lines.append(
                f"<b>Compatibilidad:</b> <span style='color:{color}'><b>"
                f"{escape(profile.status.label)}</b></span> (perfil {escape(profile.name)})"
            )
            if profile.notes:
                lines.append(f"<i>{escape(profile.notes)}</i>")
        elif details is not None and details.error is None:
            lines.append(
                "<b>Compatibilidad:</b> sin perfil (se usa la configuración por defecto; "
                "puede funcionar, pero nadie lo ha comprobado)"
            )
        self.summary.setText(_paragraphs(lines))
        self._show_state()
        self.body.setText(self._body_html())
        self._update_buttons()

    def set_activity(self, activity: Activity) -> None:
        self.activity = activity
        self._show_state()
        self._update_buttons()

    def _show_state(self) -> None:
        details = self.details
        if self.activity is not Activity.IDLE:
            text = f"<b>{escape(ACTIVITY_TEXT[self.activity])}</b>"
        elif details is None:
            text = "<i>Comprobando el juego y el sistema…</i>"
        elif details.error:
            text = f"<b style='color:#c62828'>✖ {escape(details.error)}</b>"
        elif details.ready:
            text = "<b style='color:#2e7d32'>✔ Listo para jugar</b>"
        else:
            text = (
                "<b style='color:#c62828'>✖ Falta algo para que el juego funcione</b> "
                "(mira «Requisitos» más abajo)"
            )
        self.state.setText(text)

    def _update_buttons(self) -> None:
        idle = self.activity is Activity.IDLE
        running = self.activity is Activity.RUNNING
        details = self.details
        self.play_button.setEnabled(
            idle and details is not None and details.error is None and details.analysis is not None
        )
        self.stop_button.setEnabled(running)
        self.recheck_button.setEnabled(idle and details is not None)
        self.saves_button.setEnabled(details is not None and bool(details.save_dirs))
        self.folder_button.setEnabled(self.game is not None)
        self.log_button.setEnabled(any(r.log_file for r in self.history))
        self.remove_button.setEnabled(idle)

    def _body_html(self) -> str:
        details = self.details
        parts = []
        if details is not None and details.checks:
            lines = []
            for check in details.checks:
                line = f"{CHECK_MARKS[check.status]} <b>{escape(check.label)}:</b> "
                line += escape(check.detail)
                if check.hint and check.status is not CheckStatus.OK:
                    line += f"<br>&nbsp;&nbsp;&nbsp;→ {escape(check.hint)}"
                lines.append(line)
            parts.append(_section("Requisitos", _paragraphs(lines)))

        profile = details.profile if details else None
        if details is not None and details.save_dirs:
            saves = [escape(str(p)) for p in details.save_dirs]
            saves.append(
                "<i>Están dentro del prefijo de Wine del juego: no lo borres sin copiarlas.</i>"
            )
            parts.append(_section("Partidas", _paragraphs(saves)))
        elif profile is not None and profile.save_dirs:
            parts.append(
                _section(
                    "Partidas",
                    _paragraphs(
                        [
                            "Se guardarán dentro del prefijo de Wine del juego, que se crea "
                            "la primera vez que lo lanzas."
                        ]  # fmt: skip
                    ),
                )
            )

        game = self.game
        if game is not None:
            lines = [
                f"<b>Veces jugado:</b> {game.launch_count}",
                f"<b>Tiempo de juego:</b> {format_duration(game.play_seconds)}",
                f"<b>Última vez:</b> {format_moment(game.last_played_at)}",
            ]
            if self.history:
                last = self.history[0]
                lines.append(f"<b>Último lanzamiento:</b> {escape(describe_launch(last))}")
                for issue_id in last.problems:
                    issue = find_issue(issue_id, profile)
                    if issue is None:
                        lines.append(f"⚠ {escape(issue_id)}")
                        continue
                    lines.append(
                        f"⚠ <b>{escape(issue.symptom)}</b><br>&nbsp;&nbsp;&nbsp;→ "
                        f"{escape(issue.solution)}"
                    )
            parts.append(_section("Historial", _paragraphs(lines)))

        if profile is not None and profile.known_issues:
            lines = [
                f"• <b>{escape(i.symptom)}</b><br>&nbsp;&nbsp;&nbsp;→ {escape(i.solution)}"
                for i in profile.known_issues
                if not i.harmless
            ]
            if lines:
                parts.append(_section("Problemas conocidos de este juego", _paragraphs(lines)))
        return "".join(parts)

    # --- Para la página -----------------------------------------------------

    def latest_log(self) -> Path | None:
        return next((r.log_file for r in self.history if r.log_file), None)
