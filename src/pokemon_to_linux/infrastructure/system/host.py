"""Consultas al sistema Linux: bibliotecas instaladas, sesión gráfica y montajes.

Todo es de solo lectura y no necesita privilegios. Si algo no se puede
averiguar (p. ej. no hay ``ldconfig``, como en NixOS), se devuelve ``None``
en vez de suponer que falta: un requisito desconocido no debe bloquear.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from functools import cached_property
from pathlib import Path, PurePath

from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

LDCONFIG_LOCATIONS = ("/sbin/ldconfig", "/usr/sbin/ldconfig", "/usr/bin/ldconfig")

# Marcas de ``ldconfig -p`` que indican una ABI distinta de x86 de 32 bits.
_NON_I386_FLAGS = ("x86-64", "x32", "IA-64", "AArch64", "64bit", "hard-float", "soft-float")


def parse_ldconfig(output: str) -> dict[str, set[int]]:
    """``ldconfig -p`` → ``{"libGL.so.1": {32, 64}, …}`` (solo x86: 32 = i386, 64 = x86-64).

    Formato de cada línea::

        libGL.so.1 (libc6,x86-64) => /lib/x86_64-linux-gnu/libGL.so.1
        libGL.so.1 (libc6) => /lib/i386-linux-gnu/libGL.so.1
    """
    libraries: dict[str, set[int]] = {}
    for line in output.splitlines():
        name, sep, rest = line.strip().partition(" (")
        if not sep or ") => " not in rest:
            continue
        flags = [f.strip() for f in rest.split(") => ", 1)[0].split(",")]
        if not flags or flags[0] != "libc6":
            continue
        extra = flags[1:]
        if "x86-64" in extra:
            bits = 64
        elif not any(f in _NON_I386_FLAGS for f in extra):
            bits = 32
        else:
            continue
        libraries.setdefault(name, set()).add(bits)
    return libraries


def _unescape_mount(path: str) -> str:
    """``/proc/mounts`` escapa espacios y otros caracteres como ``\\040``."""
    for code, char in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
        path = path.replace(code, char)
    return path


def parse_mounts(text: str) -> list[tuple[str, str]]:
    """``/proc/self/mounts`` → ``[(punto de montaje, tipo), …]``."""
    mounts = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            mounts.append((_unescape_mount(fields[1]), fields[2]))
    return mounts


def filesystem_of(path: PurePath, mounts: list[tuple[str, str]]) -> str | None:
    """Tipo de sistema de ficheros del montaje más específico que contiene ``path``."""
    best: tuple[int, str] | None = None
    text = path.as_posix()
    for mount_point, fstype in mounts:
        prefix = mount_point.rstrip("/") + "/"
        if (text == mount_point or text.startswith(prefix) or mount_point == "/") and (
            best is None or len(mount_point) >= best[0]
        ):
            best = (len(mount_point), fstype)
    return best[1] if best else None


X11_SOCKET_DIR = Path("/tmp/.X11-unix")  # noqa: S108 - ruta estándar de X11
_LOCAL_DISPLAY = re.compile(r"(?:unix)?:(\d+)(?:\.\d+)?")


class HostSystem:
    """Información del sistema. Las dependencias se pueden sustituir en las pruebas."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        ldconfig_locations: tuple[str, ...] = LDCONFIG_LOCATIONS,
        mounts_file: Path = Path("/proc/self/mounts"),
        x11_socket_dir: Path | None = X11_SOCKET_DIR,
        unix_sockets_file: Path = Path("/proc/net/unix"),
    ) -> None:
        self._env = os.environ if env is None else env
        self._which = which
        self._ldconfig_locations = ldconfig_locations
        self._mounts_file = mounts_file
        self._x11_socket_dir = x11_socket_dir
        self._unix_sockets_file = unix_sockets_file

    def _ldconfig(self) -> str | None:
        if found := self._which("ldconfig"):
            return found
        return next((p for p in self._ldconfig_locations if Path(p).is_file()), None)

    @cached_property
    def shared_libraries(self) -> dict[str, set[int]] | None:
        """Bibliotecas que conoce el enlazador dinámico; ``None`` si no se puede saber."""
        ldconfig = self._ldconfig()
        if ldconfig is None:
            log.info("ldconfig no encontrado: no se pueden comprobar las bibliotecas")
            return None
        try:
            proc = subprocess.run(
                [ldconfig, "-p"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("ldconfig -p falló: %s", exc)
            return None
        if proc.returncode != 0:
            log.warning("ldconfig -p devolvió %s", proc.returncode)
            return None
        return parse_ldconfig(proc.stdout)

    def has_library(self, name: str, bits: int) -> bool | None:
        libraries = self.shared_libraries
        if libraries is None:
            return None
        return bits in libraries.get(name, set())

    def libraries_matching(self, prefix: str, suffix: str, bits: int) -> list[str] | None:
        libraries = self.shared_libraries
        if libraries is None:
            return None
        return sorted(
            n
            for n, b in libraries.items()
            if n.startswith(prefix) and n.endswith(suffix) and bits in b
        )

    @property
    def x11_display(self) -> str | None:
        return self._env.get("DISPLAY") or None

    def x11_socket(self) -> Path | None:
        """Socket del servidor X de ``DISPLAY`` si es local (``:0``, ``:1.0``, ``unix:0``).

        ``None`` si no se puede saber: pantalla remota (``localhost:10.0`` con
        ``ssh -X``) o sin carpeta de sockets que mirar.
        """
        display = self.x11_display
        if not display or self._x11_socket_dir is None:
            return None
        match = _LOCAL_DISPLAY.fullmatch(display)
        return self._x11_socket_dir / f"X{match.group(1)}" if match else None

    def x11_server_listening(self) -> bool | None:
        """¿Hay un servidor X escuchando en el socket de ``DISPLAY``? ``None`` si no se sabe.

        El servidor puede escuchar solo en un socket abstracto (``@/tmp/.X11-unix/X1``),
        sin fichero: pasa con Xvfb en WSL, donde ``/tmp/.X11-unix`` es de WSLg.
        Los abstractos se ven en ``/proc/net/unix``.
        """
        socket = self.x11_socket()
        if socket is None:
            return None
        if socket.exists():
            return True
        try:
            table = self._unix_sockets_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        name = socket.as_posix()
        return any(line.split()[-1] in (name, f"@{name}") for line in table.splitlines()[1:]
                   if line.split())  # fmt: skip

    @property
    def wayland_display(self) -> str | None:
        return self._env.get("WAYLAND_DISPLAY") or None

    def filesystem_type(self, path: Path) -> str | None:
        try:
            mounts = parse_mounts(self._mounts_file.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
        return filesystem_of(path.resolve(), mounts)
