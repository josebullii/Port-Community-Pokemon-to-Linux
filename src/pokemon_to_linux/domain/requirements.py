"""Resultado de comprobar un requisito del sistema antes de lanzar un juego."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    """Se puede jugar, pero algo irá peor (p. ej. carga lenta)."""
    ERROR = "error"
    """El juego no funcionará hasta resolverlo."""
    UNKNOWN = "unknown"
    """No se ha podido comprobar. No bloquea el lanzamiento."""


@dataclass(frozen=True, slots=True)
class RequirementCheck:
    id: str
    label: str
    status: CheckStatus
    detail: str
    hint: str = ""
    """Qué hacer para resolverlo (si no está bien)."""

    @property
    def blocking(self) -> bool:
        return self.status is CheckStatus.ERROR

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status.value,
            "detail": self.detail,
            "hint": self.hint,
        }
