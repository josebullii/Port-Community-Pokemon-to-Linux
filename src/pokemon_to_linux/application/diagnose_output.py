"""Caso de uso: reconocer problemas conocidos en la salida de un juego.

Se alimenta línea a línea mientras el juego se ejecuta (``feed``) y al
terminar resume qué ha pasado y qué hacer. Los patrones son texto literal
(nunca expresiones regulares) para que un perfil no pueda colgar el
programa con un patrón patológico.

Primero se buscan los problemas del perfil del juego y después los
generales (de Wine y mkxp-z). Así, un perfil puede declarar como
inofensivo (``harmless``) un mensaje que, sin él, parecería un error: la
línea que reconoce el perfil ya no se compara con los generales.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_to_linux.application.check_requirements import OPENGL_HINTS
from pokemon_to_linux.domain.profile import GameProfile, KnownIssue

MAX_LINE = 4096
"""Las líneas más largas se recortan antes de buscar en ellas."""

GENERIC_ISSUES = (
    KnownIssue(
        id="opengl-sin-formato",
        symptom="El juego no puede crear su ventana OpenGL.",
        solution=(
            "Suele faltar OpenGL con los bits del juego (de 32 bits para Pokémon Z). "
            + OPENGL_HINTS[32]
        ),
        # Wine avisa antes que mkxp-z (si WINEDEBUG conserva los err).
        output=("Failed to load libGL", "No matching GL pixel format available"),
    ),
    KnownIssue(
        id="wine32-falta",
        symptom="Wine no puede ejecutar programas de 32 bits.",
        solution=(
            "Debian/Ubuntu: sudo dpkg --add-architecture i386 && sudo apt update && "
            "sudo apt install wine32:i386. En otras distribuciones, instala el soporte "
            "de 32 bits (multilib) de Wine."
        ),
        output=("it looks like wine32 is missing",),
    ),
    KnownIssue(
        id="dll-no-encontrada",
        symptom="Falta una DLL que necesita el juego.",
        solution="Mira en el log qué DLL no se encuentra (import_dll) y si viene con el juego.",
        output=("err:module:import_dll",),
    ),
    KnownIssue(
        id="audio-no-disponible",
        symptom="El juego no puede abrir el dispositivo de audio y se cierra.",
        solution=(
            "Comprueba que el sonido funciona (pactl info) y vuelve a lanzarlo; a veces "
            "falla al relanzar justo después de cerrar. Con Wine de 32 bits hace falta "
            "PulseAudio de 32 bits (Debian/Ubuntu: libpulse0:i386)."
        ),
        output=("Error opening OpenAL device",),
    ),
    KnownIssue(
        id="sin-pantalla",
        symptom="Wine no encuentra la sesión gráfica.",
        solution="Lanza el juego desde el escritorio (hace falta X11 o XWayland).",
        output=("Make sure that your X server is running", "cannot open display"),
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    issue: KnownIssue
    line: str
    """Primera línea de la salida en la que se reconoció."""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.issue.id,
            "symptom": self.issue.symptom,
            "solution": self.issue.solution,
            "line": self.line,
            "harmless": self.issue.harmless,
        }


class OutputDiagnoser:
    def __init__(self, profile: GameProfile | None = None) -> None:
        issues: list[KnownIssue] = []
        if profile is not None:
            issues += [i for i in profile.known_issues if i.output]
        self._issues = [*issues, *GENERIC_ISSUES]
        self._seen: set[str] = set()
        self._findings: list[Finding] = []

    def feed(self, line: str) -> Finding | None:
        """Analiza una línea. Devuelve el problema si es la primera vez que aparece."""
        text = line[:MAX_LINE]
        for issue in self._issues:
            if issue.found_in(text):
                # La línea es de este problema aunque ya se haya informado:
                # no se compara con los siguientes (p. ej. los generales).
                if issue.id in self._seen:
                    return None
                self._seen.add(issue.id)
                finding = Finding(issue, line.strip()[:300])
                self._findings.append(finding)
                return finding
        return None

    def feed_all(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.feed(line)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings)

    @property
    def problems(self) -> tuple[Finding, ...]:
        """Los hallazgos que no son inofensivos."""
        return tuple(f for f in self._findings if not f.issue.harmless)
