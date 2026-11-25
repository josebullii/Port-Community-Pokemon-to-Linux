"""Piezas de interfaz pequeñas que comparten las páginas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def wrapping_label(text: str = "", *, rich: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def page(title: str, body: QWidget, *, stretch: bool = True) -> QWidget:
    """Página con un título y su contenido."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    heading = QLabel(f"<h2>{title}</h2>")
    heading.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(heading)
    layout.addWidget(body, 0 if stretch else 1)
    if stretch:
        layout.addStretch(1)
    return widget
