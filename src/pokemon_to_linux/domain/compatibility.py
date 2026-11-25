"""Estado de compatibilidad de un juego (el mismo que la matriz de docs/compatibility.md)."""

from __future__ import annotations

from enum import StrEnum


class CompatibilityStatus(StrEnum):
    NOT_TESTED = "not_tested"
    NOT_WORKING = "not_working"
    PARTIAL = "partial"
    """Se puede jugar, pero hay fallos conocidos o funciones sin comprobar."""
    COMPATIBLE = "compatible"
    """Pasa todas las funciones de la lista de pruebas."""

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    CompatibilityStatus.NOT_TESTED: "No probado",
    CompatibilityStatus.NOT_WORKING: "No funciona",
    CompatibilityStatus.PARTIAL: "Parcial",
    CompatibilityStatus.COMPATIBLE: "Compatible",
}
