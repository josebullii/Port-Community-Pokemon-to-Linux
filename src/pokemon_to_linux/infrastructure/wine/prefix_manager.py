"""Prefijos Wine aislados, uno por juego.

Decisiones (comprobadas con Wine 9.0 en Ubuntu 24.04):

- **win64 por defecto, también para juegos de 32 bits.** Un prefijo win64
  ejecuta programas de 32 bits mediante WoW64 si el sistema tiene soporte
  de 32 bits, y las versiones de Wine solo-WoW64 ya no crean prefijos
  win32. win32 queda como opción explícita (p. ej. en un perfil).
- ``wineboot --init`` vuelve antes de que el registro esté en disco:
  ``wineserver -w`` espera a que se escriba ``system.reg``.
- Un prefijo existente nunca se recrea ni se borra sin que se pida.
"""

from __future__ import annotations

import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.wine.test_program import write_exit_program
from pokemon_to_linux.infrastructure.wine.wine_manager import (
    Runner,
    WineError,
    WineInstallation,
    run_command,
    wine_environment,
)

log = get_logger(__name__)

ARCHES = ("win32", "win64")
DEFAULT_ARCH = "win64"
TEST_EXIT_CODE = 42

_GAME_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ARCH_LINE = re.compile(r"^#arch=(win32|win64)\s*$", re.MULTILINE)


class PrefixError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Prefix:
    game_id: str
    path: Path
    arch: str


@dataclass(frozen=True, slots=True)
class TestProgramResult:
    bits: int
    ok: bool
    exit_code: int | None
    output: str


def slugify(name: str) -> str:
    """``Pokémon Z v2.19`` → ``pokemon-z-v2.19`` (identificador válido de prefijo)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9.]+", "-", ascii_name.lower()).strip("-.")
    return slug[:64].rstrip("-.") or "juego"


def validate_game_id(game_id: str) -> str:
    if not _GAME_ID.match(game_id) or ".." in game_id:
        raise PrefixError(f"Identificador de juego no válido: {game_id!r}")
    return game_id


def resolve_arch(exe_bits: int | None, requested: str | None = None) -> str:
    """Arquitectura del prefijo para un ejecutable de ``exe_bits`` bits."""
    if requested is not None and requested not in ARCHES:
        raise PrefixError(f"Arquitectura no válida: {requested!r} (usa win32 o win64)")
    if requested == "win32" and exe_bits == 64:
        raise PrefixError("Un prefijo win32 no puede ejecutar un programa de 64 bits")
    return requested or DEFAULT_ARCH


def read_prefix_arch(path: Path) -> str | None:
    """Lee ``#arch=…`` de ``system.reg``; ``None`` si el prefijo no está creado."""
    try:
        head = (path / "system.reg").read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    match = _ARCH_LINE.search(head)
    return match[1] if match else None


class PrefixManager:
    def __init__(
        self,
        prefixes_dir: Path,
        wine: WineInstallation,
        *,
        runner: Runner = run_command,
        init_timeout: float = 300,
        registry_wait: float = 30,
    ) -> None:
        self.prefixes_dir = prefixes_dir
        self.wine = wine
        self._run = runner
        self._init_timeout = init_timeout
        self._registry_wait = registry_wait

    # --- Consulta -----------------------------------------------------------

    def path_for(self, game_id: str) -> Path:
        return self.prefixes_dir / validate_game_id(game_id)

    def get(self, game_id: str) -> Prefix | None:
        path = self.path_for(game_id)
        arch = read_prefix_arch(path)
        return Prefix(game_id, path, arch) if arch else None

    def environment(self, prefix: Prefix, **kwargs) -> dict[str, str]:
        return wine_environment(prefix.path, **kwargs)

    # --- Creación -----------------------------------------------------------

    def ensure(self, game_id: str, arch: str = DEFAULT_ARCH) -> Prefix:
        """Devuelve el prefijo del juego, creándolo si no existe."""
        existing = self.get(game_id)
        if existing is None:
            return self.create(game_id, arch)
        if existing.arch != arch:
            raise PrefixError(
                f"El prefijo de {game_id} ya existe como {existing.arch} y se ha pedido {arch}. "
                "Bórralo para recrearlo con otra arquitectura."
            )
        return existing

    def create(self, game_id: str, arch: str = DEFAULT_ARCH) -> Prefix:
        resolve_arch(None, arch)
        path = self.path_for(game_id)
        if path.exists() and any(path.iterdir()):
            raise PrefixError(f"Ya existe una carpeta en {path}; no se sobrescribe.")
        self.prefixes_dir.mkdir(parents=True, exist_ok=True)

        env = wine_environment(path, arch=arch)
        log.info("Creando prefijo %s (%s) en %s", game_id, arch, path)
        started = time.monotonic()
        try:
            result = self._run([str(self.wine.wine), "wineboot", "--init"], env,
                               self._init_timeout, None)  # fmt: skip
            if result.returncode != 0:
                raise PrefixError(
                    f"wineboot falló (código {result.returncode}): {_tail(result.output)}"
                )
            self._wait_for_registry(path, env)
            created = read_prefix_arch(path)
            if created != arch:
                raise PrefixError(
                    f"El prefijo se creó como {created or 'desconocido'} en vez de {arch}. "
                    "Puede que esta versión de Wine no admita prefijos de esa arquitectura."
                )
        except (PrefixError, WineError):
            self._remove(path)  # no dejar prefijos a medio crear
            raise
        log.info("Prefijo %s listo en %.1f s", game_id, time.monotonic() - started)
        return Prefix(game_id, path, arch)

    def _wait_for_registry(self, path: Path, env: dict[str, str]) -> None:
        if self.wine.wineserver is not None:
            self._run([str(self.wine.wineserver), "-w"], env, self._registry_wait, None)
        deadline = time.monotonic() + self._registry_wait
        while read_prefix_arch(path) is None and time.monotonic() < deadline:
            time.sleep(0.2)

    # --- Mantenimiento ------------------------------------------------------

    def kill(self, prefix: Prefix) -> None:
        """Cierra todos los procesos Wine de este prefijo (``wineserver -k``)."""
        if self.wine.wineserver is None:
            log.warning("Sin wineserver: no se pueden cerrar los procesos de %s", prefix.game_id)
            return
        self._run([str(self.wine.wineserver), "-k"], self.environment(prefix), 30, None)

    def delete(self, game_id: str) -> bool:
        path = self.path_for(game_id)
        if not path.exists():
            return False
        if (prefix := self.get(game_id)) is not None:
            self.kill(prefix)
        self._remove(path)
        log.info("Prefijo %s borrado", game_id)
        return True

    def _remove(self, path: Path) -> None:
        # Doble comprobación antes de borrar nada.
        if path.is_symlink() or path.resolve().parent != self.prefixes_dir.resolve():
            raise PrefixError(f"Ruta de prefijo sospechosa, no se borra: {path}")
        if path.exists():
            shutil.rmtree(path)

    # --- Comprobación -------------------------------------------------------

    def run_test_program(
        self, prefix: Prefix, bits: int, timeout: float = 120
    ) -> TestProgramResult:
        """Ejecuta el programa de prueba de ``bits`` bits dentro del prefijo."""
        exe = prefix.path / "drive_c" / "pokemon-to-linux" / f"prueba_{bits}.exe"
        write_exit_program(exe, TEST_EXIT_CODE, bits=bits)
        try:
            result = self._run([str(self.wine.wine), str(exe)], self.environment(prefix),
                               timeout, None)  # fmt: skip
        except WineError as exc:
            return TestProgramResult(bits, False, None, str(exc))
        ok = result.returncode == TEST_EXIT_CODE
        log.info("Programa de prueba de %s bits en %s: código %s", bits, prefix.game_id,
                 result.returncode)  # fmt: skip
        return TestProgramResult(bits, ok, result.returncode, result.output)


def _tail(text: str, lines: int = 5) -> str:
    return " | ".join(text.strip().splitlines()[-lines:])
