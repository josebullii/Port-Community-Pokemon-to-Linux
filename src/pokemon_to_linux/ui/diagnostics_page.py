"""Página «Diagnóstico»: versiones, rutas de la aplicación, Wine y OpenGL.

``wine --version`` y ``ldconfig -p`` suelen tardar milisegundos, pero si se
colgaran bloquearían la ventana hasta su tiempo límite (30 y 15 s): se
ejecutan con ``TaskRunner``.
"""

from __future__ import annotations

import platform
import sys

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QFormLayout, QPushButton, QVBoxLayout, QWidget

from pokemon_to_linux import __version__
from pokemon_to_linux.application.check_requirements import check_system_opengl
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.domain.requirements import CheckStatus
from pokemon_to_linux.infrastructure.wine.wine_manager import WineError, WineManager
from pokemon_to_linux.ui.tasks import TaskRunner
from pokemon_to_linux.ui.widgets import wrapping_label

CHECKING = "Comprobando…"


def wine_status() -> str:
    try:
        wine = WineManager().detect()
    except WineError as exc:
        return f"error: {exc}"
    if wine is None:
        return "no instalado (instálalo desde los repositorios de tu distribución)"
    return f"{wine.description} ({wine.wine})"


STATUS_WORDS = {
    CheckStatus.OK: "sí",
    CheckStatus.WARNING: "aviso",
    CheckStatus.ERROR: "NO",
    CheckStatus.UNKNOWN: "no se sabe",
}


def opengl_status() -> str:
    """OpenGL de 32 y 64 bits. Pokémon Z y otros juegos mkxp-z de 32 bits necesitan el de 32."""
    parts = []
    for check in check_system_opengl():
        text = f"{check.label}: {STATUS_WORDS[check.status]}"
        if check.status is CheckStatus.OK:
            text += f" ({check.detail})"
        elif check.hint:
            text += f". {check.hint}"
        parts.append(text)
    return "\n".join(parts)


class DiagnosticsPage(QWidget):
    def __init__(
        self, paths: AppPaths, log_file: str | None, tasks: TaskRunner, parent=None
    ) -> None:
        super().__init__(parent)
        self._tasks = tasks
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        rows = {
            "Versión": __version__,
            "Python": sys.version.split()[0],
            "PySide6 / Qt": f"{pyside_version} / {qVersion()}",
            "Sistema": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "Datos": str(paths.data_dir),
            "Biblioteca": str(paths.database_path),
            "Prefijos": str(paths.prefixes_dir),
            "Configuración": str(paths.config_dir),
            "Caché": str(paths.cache_dir),
            "Estado": str(paths.state_dir),
            "Log": log_file or "(sin fichero)",
        }
        for key, value in rows.items():
            form.addRow(f"{key}:", wrapping_label(value))
        self.wine_label = wrapping_label(CHECKING)
        self.opengl_label = wrapping_label(CHECKING)
        form.addRow("Wine:", self.wine_label)
        form.addRow("OpenGL:", self.opengl_label)

        self.refresh_button = QPushButton("Volver a comprobar")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form_widget)
        layout.addWidget(self.refresh_button)
        self.refresh()

    def refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.wine_label.setText(CHECKING)
        self.opengl_label.setText(CHECKING)

        def failed(exc: object) -> None:
            self.refresh_button.setEnabled(True)
            self.wine_label.setText(f"error inesperado: {exc}")
            self.opengl_label.setText(f"error inesperado: {exc}")

        self._tasks.run(
            lambda: (wine_status(), opengl_status()),
            self._show,
            failed,
            name="comprobación de Wine y OpenGL",
        )

    def _show(self, result: tuple[str, str]) -> None:
        wine, opengl = result
        self.wine_label.setText(wine)
        self.opengl_label.setText(opengl)
        self.refresh_button.setEnabled(True)
