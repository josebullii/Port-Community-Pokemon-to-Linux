"""Detección de Wine y entorno de ejecución.

La aplicación nunca instala Wine: si no lo encuentra, lo dice claramente.
Los comandos se ejecutan siempre con listas de argumentos (nunca
``shell=True``) y con tiempo límite.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

WINE_NAMES = ("wine", "wine64")
# Rutas habituales fuera del PATH (p. ej. Ubuntu con solo el paquete wine64,
# o los paquetes oficiales de WineHQ en /opt).
KNOWN_LOCATIONS = (
    "/usr/lib/wine/wine64",
    "/usr/lib/wine/wine",
    "/opt/wine-stable/bin/wine",
    "/opt/wine-staging/bin/wine",
    "/opt/wine-devel/bin/wine",
)
WINESERVER_NAMES = ("wineserver", "wineserver64")
KNOWN_WINESERVERS = ("/usr/lib/wine/wineserver", "/usr/lib/wine/wineserver64")

# Evita que Wine ofrezca instalar Mono/Gecko con ventanas emergentes.
DEFAULT_DLL_OVERRIDES = "mscoree=;mshtml="

_VERSION_RE = re.compile(r"^wine-(?P<version>\S+?)(?:\s+\((?P<flavor>[^)]*)\))?\s*$")


class WineError(RuntimeError):
    """Fallo al ejecutar Wine o una de sus herramientas."""


class WineTimeoutError(WineError):
    pass


class CommandResult(NamedTuple):
    returncode: int
    output: str


Runner = Callable[[Sequence[str], Mapping[str, str], float, "Path | None"], CommandResult]


def run_command(
    args: Sequence[str], env: Mapping[str, str], timeout: float, cwd: Path | None = None
) -> CommandResult:
    """Ejecuta un comando (lista de argumentos) y devuelve código y salida combinada."""
    try:
        proc = subprocess.run(
            list(args),
            env=dict(env),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            text=True,
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise WineError(f"No se encuentra el programa: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise WineTimeoutError(f"{Path(args[0]).name} no terminó en {timeout:.0f} s") from exc
    return CommandResult(proc.returncode, proc.stdout or "")


@dataclass(frozen=True, slots=True)
class WineInstallation:
    wine: Path
    wineserver: Path | None
    version: str
    """Versión limpia, p. ej. ``9.0`` o ``10.0-rc1``."""
    flavor: str | None
    """Lo que va entre paréntesis: ``Staging``, ``Ubuntu 9.0~repack-4build3``…"""
    description: str
    """Salida completa de ``wine --version``."""

    @property
    def version_tuple(self) -> tuple[int, ...]:
        numbers = re.findall(r"\d+", self.version.split("-")[0])
        return tuple(int(n) for n in numbers)


def parse_version(text: str) -> tuple[str, str | None]:
    """``wine-9.0 (Ubuntu 9.0~repack-4build3)`` → ``("9.0", "Ubuntu 9.0~repack-4build3")``."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    match = _VERSION_RE.match(line)
    if match is None:
        raise WineError(f"Versión de Wine no reconocida: {line!r}")
    return match["version"], match["flavor"]


def wine_environment(
    prefix: Path,
    *,
    arch: str | None = None,
    debug: str = "-all",
    dll_overrides: str = DEFAULT_DLL_OVERRIDES,
    extra: Mapping[str, str] | None = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Entorno para ejecutar Wine sobre ``prefix``.

    Parte del entorno actual pero descarta cualquier ``WINE*`` heredado,
    para que un ``WINEPREFIX`` del usuario no se mezcle con el del juego.
    """
    env = {k: v for k, v in (os.environ if base is None else base).items()}
    for key in [k for k in env if k.startswith("WINE")]:
        del env[key]
    env["WINEPREFIX"] = str(prefix)
    env["WINEDEBUG"] = debug
    if dll_overrides:
        env["WINEDLLOVERRIDES"] = dll_overrides
    if arch:
        env["WINEARCH"] = arch
    env.update(extra or {})
    return env


class WineManager:
    def __init__(
        self,
        wine_path: Path | str | None = None,
        *,
        runner: Runner = run_command,
        which: Callable[[str], str | None] = shutil.which,
        known_locations: Sequence[str] = KNOWN_LOCATIONS,
        known_wineservers: Sequence[str] = KNOWN_WINESERVERS,
    ) -> None:
        self._explicit = Path(wine_path) if wine_path else None
        self._runner = runner
        self._which = which
        self._known = known_locations
        self._known_servers = known_wineservers

    def find_wine(self) -> Path | None:
        if self._explicit is not None:
            return self._explicit if _is_executable(self._explicit) else None
        for name in WINE_NAMES:
            if found := self._which(name):
                return Path(found)
        return next((Path(p) for p in self._known if _is_executable(Path(p))), None)

    def find_wineserver(self, wine: Path) -> Path | None:
        for name in WINESERVER_NAMES:
            sibling = wine.parent / name
            if _is_executable(sibling):
                return sibling
        for name in WINESERVER_NAMES:
            if found := self._which(name):
                return Path(found)
        return next((Path(p) for p in self._known_servers if _is_executable(Path(p))), None)

    def detect(self) -> WineInstallation | None:
        """Devuelve la instalación de Wine, o ``None`` si no hay ninguna.

        Lanza ``WineError`` si Wine existe pero no responde correctamente.
        """
        wine = self.find_wine()
        if wine is None:
            log.info("Wine no encontrado")
            return None
        result = self._runner([str(wine), "--version"], dict(os.environ), 30, None)
        if result.returncode != 0:
            raise WineError(f"{wine} --version falló (código {result.returncode})")
        version, flavor = parse_version(result.output)
        installation = WineInstallation(
            wine=wine,
            wineserver=self.find_wineserver(wine),
            version=version,
            flavor=flavor,
            description=result.output.strip().splitlines()[0],
        )
        log.info("Wine detectado: %s (%s)", installation.description, wine)
        return installation


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
