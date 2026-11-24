"""Inventario de la carpeta de un juego.

El escáner solo lee metadatos (nombres, tamaños); no abre ficheros. Reglas:

- no sigue enlaces simbólicos (se anotan y se omiten);
- se detiene al llegar a ``max_files`` y marca el resultado como truncado;
- las búsquedas por nombre no distinguen mayúsculas, porque los juegos de
  Windows mezclan ``Data/`` y ``data/`` y en Linux eso importa.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

DEFAULT_MAX_FILES = 200_000


class GameScanError(ValueError):
    """La ruta indicada no es una carpeta de juego válida."""


@dataclass(frozen=True, slots=True)
class GameScan:
    root: Path
    files: tuple[str, ...]
    """Ficheros del primer nivel (nombre real)."""
    directories: tuple[str, ...]
    """Subcarpetas del primer nivel (nombre real)."""
    relative_files: tuple[str, ...]
    """Todos los ficheros, como rutas relativas con ``/``."""
    total_size: int
    extension_counts: dict[str, int] = field(default_factory=dict)
    skipped_symlinks: tuple[str, ...] = ()
    unreadable: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def total_files(self) -> int:
        return len(self.relative_files)

    def find_file(self, name: str) -> str | None:
        """Nombre real de un fichero del primer nivel, sin distinguir mayúsculas."""
        return _find(self.files, name)

    def find_dir(self, name: str) -> str | None:
        """Nombre real de una subcarpeta del primer nivel, sin distinguir mayúsculas."""
        return _find(self.directories, name)

    def find_relative(self, relative: str) -> str | None:
        """Ruta real de un fichero (``Data\\Scripts.rxdata`` o ``data/scripts.rxdata``)."""
        wanted = _normalize(relative)
        for candidate in self.relative_files:
            if candidate.lower() == wanted:
                return candidate
        return None

    def files_with_suffix(self, suffix: str, directory: str | None = None) -> tuple[str, ...]:
        """Ficheros con esa extensión en el primer nivel o en ``directory`` (sin recursión)."""
        suffix = suffix.lower()
        prefix = ""
        if directory is not None:
            real_dir = self.find_dir(directory)
            if real_dir is None:
                return ()
            prefix = real_dir.lower() + "/"
        result = []
        for rel in self.relative_files:
            lower = rel.lower()
            if not lower.startswith(prefix) or not lower.endswith(suffix):
                continue
            if "/" not in lower[len(prefix) :]:
                result.append(rel)
        return tuple(result)

    def path_of(self, relative: str) -> Path:
        return self.root.joinpath(*PurePosixPath(relative).parts)


def _normalize(relative: str) -> str:
    return relative.replace("\\", "/").strip("/").lower()


def _find(names: tuple[str, ...], wanted: str) -> str | None:
    wanted = wanted.lower()
    return next((n for n in names if n.lower() == wanted), None)


class GameScanner:
    def __init__(self, max_files: int = DEFAULT_MAX_FILES) -> None:
        self.max_files = max_files

    def scan(self, path: Path | str) -> GameScan:
        root = Path(path).expanduser()
        if not root.exists():
            raise GameScanError(f"La ruta no existe: {root}")
        if not root.is_dir():
            raise GameScanError(f"La ruta no es una carpeta: {root}")
        root = root.resolve()

        top_files: list[str] = []
        top_dirs: list[str] = []
        relative_files: list[str] = []
        symlinks: list[str] = []
        unreadable: list[str] = []
        extensions: Counter[str] = Counter()
        total_size = 0
        truncated = False

        pending: list[tuple[Path, str]] = [(root, "")]
        while pending and not truncated:
            current, rel_dir = pending.pop()
            try:
                entries = sorted(os.scandir(current), key=lambda e: e.name)
            except OSError as exc:
                unreadable.append(rel_dir or ".")
                log.warning("No se puede leer %s: %s", current, exc)
                continue

            for entry in entries:
                rel = f"{rel_dir}{entry.name}"
                if entry.is_symlink():
                    symlinks.append(rel)
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if not rel_dir:
                            top_dirs.append(entry.name)
                        pending.append((Path(entry.path), rel + "/"))
                    elif entry.is_file(follow_symlinks=False):
                        if len(relative_files) >= self.max_files:
                            truncated = True
                            break
                        if not rel_dir:
                            top_files.append(entry.name)
                        relative_files.append(rel)
                        total_size += entry.stat(follow_symlinks=False).st_size
                        extensions[os.path.splitext(entry.name)[1].lower()] += 1
                except OSError as exc:
                    unreadable.append(rel)
                    log.warning("No se puede leer %s: %s", entry.path, exc)

        if truncated:
            log.warning("Escaneo truncado en %s ficheros: %s", self.max_files, root)

        return GameScan(
            root=root,
            files=tuple(top_files),
            directories=tuple(top_dirs),
            relative_files=tuple(sorted(relative_files)),
            total_size=total_size,
            extension_counts=dict(extensions.most_common()),
            skipped_symlinks=tuple(sorted(symlinks)),
            unreadable=tuple(sorted(unreadable)),
            truncated=truncated,
        )
