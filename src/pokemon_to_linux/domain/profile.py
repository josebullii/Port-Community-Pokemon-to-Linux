"""Perfiles de compatibilidad de juegos.

Un perfil dice cómo reconocer un juego concreto y qué necesita para
funcionar: arquitectura del prefijo, variables de entorno, dónde guarda las
partidas y qué problemas conocidos tiene.

Son **datos declarativos que se validan antes de usarlos**, nunca scripts:

- Las claves desconocidas son un error (una errata no debe pasar inadvertida).
- Solo se admiten variables de entorno de una lista cerrada. Nada de
  ``LD_PRELOAD``, ``PATH`` ni ``WINE*``, que podrían ejecutar código o
  romper el aislamiento del prefijo.
- Las rutas de partidas parten de una carpeta conocida (``%USERPROFILE%``,
  ``%APPDATA%``…) y no pueden salir de ella con ``..``.
- Los patrones de salida son texto literal, no expresiones regulares.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import PureWindowsPath
from typing import Any

from pokemon_to_linux.domain.compatibility import CompatibilityStatus

SCHEMA_VERSION = 1

ARCHES = ("win32", "win64")

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

ALLOWED_ENVIRONMENT = re.compile(
    r"^(LANG|LANGUAGE|LC_[A-Z]+|TZ|SDL_[A-Z0-9_]+|MESA_[A-Z0-9_]+|LIBGL_[A-Z0-9_]+"
    r"|__GL_[A-Z0-9_]+|vblank_mode|PULSE_LATENCY_MSEC)$"
)
MAX_ENV_VALUE = 256

GAME_DIR = "%GAMEDIR%"
FOLDER_ROOTS = ("%USERPROFILE%", "%APPDATA%", "%LOCALAPPDATA%", GAME_DIR)
"""Carpetas desde las que puede partir una ruta de partidas o de configuración."""


class ProfileError(ValueError):
    """Perfil mal formado. El mensaje indica el fichero y el campo."""


@dataclass(frozen=True, slots=True)
class ProfileMatch:
    """Condiciones para que un perfil se aplique a un juego. Todas deben cumplirse."""

    engine: str | None = None
    runtimes: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    """Valores de ``Title=`` en ``Game.ini`` (sin distinguir mayúsculas)."""
    files: tuple[str, ...] = ()
    """Ficheros que deben existir en la carpeta del juego."""

    @property
    def specificity(self) -> int:
        """Cuántas condiciones tiene: con varios perfiles válidos gana el más específico."""
        return (self.engine is not None) + bool(self.runtimes) + bool(self.titles) + len(self.files)

    def matches(
        self,
        *,
        engine: str,
        runtime: str,
        title: str | None,
        has_file: Callable[[str], bool],
    ) -> bool:
        if self.engine is not None and engine != self.engine:
            return False
        if self.runtimes and runtime not in self.runtimes:
            return False
        if self.titles:
            wanted = {t.casefold() for t in self.titles}
            if title is None or title.strip().casefold() not in wanted:
                return False
        return all(has_file(f) for f in self.files)


@dataclass(frozen=True, slots=True)
class KnownIssue:
    id: str
    symptom: str
    solution: str
    output: tuple[str, ...] = ()
    """Textos que, si aparecen en la salida del juego, indican este problema."""
    harmless: bool = False
    """Mensaje esperado que no afecta al juego (p. ej. una DLL opcional que no carga)."""

    def found_in(self, line: str) -> bool:
        return any(pattern in line for pattern in self.output)


@dataclass(frozen=True, slots=True)
class GameProfile:
    id: str
    name: str
    match: ProfileMatch
    description: str = ""
    arch: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    save_dirs: tuple[str, ...] = ()
    config_dirs: tuple[str, ...] = ()
    known_issues: tuple[KnownIssue, ...] = ()
    status: CompatibilityStatus = CompatibilityStatus.NOT_TESTED
    notes: str = ""
    source: str = ""
    """De dónde se cargó (fichero), para los mensajes de error y el diagnóstico."""


# --- Lectura y validación ---------------------------------------------------------


class _Section:
    """Lee una tabla comprobando tipos y rechazando claves desconocidas."""

    def __init__(self, data: Any, where: str) -> None:
        if not isinstance(data, Mapping):
            raise ProfileError(f"{where}: debe ser una tabla")
        self._data = data
        self._where = where
        self._used: set[str] = set()

    def _get(self, key: str, kind: type | tuple[type, ...], required: bool) -> Any:
        self._used.add(key)
        if key not in self._data:
            if required:
                raise ProfileError(f"{self._where}: falta el campo obligatorio {key!r}")
            return None
        value = self._data[key]
        if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
            raise ProfileError(f"{self._where}.{key}: tipo no válido")
        return value

    def text(self, key: str, *, required: bool = False, default: str = "") -> str:
        value = self._get(key, str, required)
        if value is None:
            return default
        if "\0" in value:
            raise ProfileError(f"{self._where}.{key}: contiene caracteres no válidos")
        return value

    def texts(self, key: str) -> tuple[str, ...]:
        value = self._get(key, list, False) or []
        if not all(isinstance(v, str) and v and "\0" not in v for v in value):
            raise ProfileError(f"{self._where}.{key}: debe ser una lista de textos no vacíos")
        return tuple(value)

    def boolean(self, key: str) -> bool:
        return bool(self._get(key, bool, False))

    def integer(self, key: str, *, required: bool = False) -> int | None:
        return self._get(key, int, required)

    def section(self, key: str) -> _Section:
        self._used.add(key)
        return _Section(self._data.get(key, {}), f"{self._where}.{key}")

    def tables(self, key: str) -> list[_Section]:
        value = self._get(key, list, False) or []
        return [_Section(item, f"{self._where}.{key}[{i}]") for i, item in enumerate(value)]

    def raw(self, key: str) -> Mapping[str, Any]:
        self._used.add(key)
        value = self._data.get(key, {})
        if not isinstance(value, Mapping):
            raise ProfileError(f"{self._where}.{key}: debe ser una tabla")
        return value

    def done(self) -> None:
        unknown = sorted(set(self._data) - self._used)
        if unknown:
            raise ProfileError(f"{self._where}: campos desconocidos: {', '.join(unknown)}")


def _check_id(value: str, where: str) -> str:
    if not _ID.match(value) or ".." in value:
        raise ProfileError(
            f"{where}: identificador no válido {value!r} "
            "(minúsculas, números, '.', '-' y '_'; hasta 64 caracteres)"
        )
    return value


def _check_environment(env: Mapping[str, Any], where: str) -> dict[str, str]:
    checked: dict[str, str] = {}
    for key, value in env.items():
        if not ALLOWED_ENVIRONMENT.match(key):
            raise ProfileError(f"{where}: variable de entorno no permitida: {key}")
        if not isinstance(value, str) or "\0" in value or len(value) > MAX_ENV_VALUE:
            raise ProfileError(f"{where}.{key}: el valor debe ser un texto corto")
        checked[key] = value
    return checked


def check_folder(path: str, where: str) -> str:
    """Valida una ruta como ``%USERPROFILE%/Saved Games/Juego`` y la normaliza con ``/``."""
    parts = PureWindowsPath(path).parts
    if not parts or parts[0].upper() not in FOLDER_ROOTS:
        raise ProfileError(f"{where}: la ruta {path!r} debe empezar por {', '.join(FOLDER_ROOTS)}")
    rest = parts[1:]
    if any(p in ("..", ".") or ":" in p for p in rest):
        raise ProfileError(f"{where}: la ruta {path!r} no puede salir de su carpeta")
    return "/".join((parts[0].upper(), *rest))


def _check_relative_file(path: str, where: str) -> str:
    pure = PureWindowsPath(path)
    if pure.is_absolute() or pure.drive or any(p == ".." for p in pure.parts):
        raise ProfileError(f"{where}: {path!r} debe ser una ruta relativa dentro del juego")
    return "/".join(pure.parts)


def parse_profile(data: Mapping[str, Any], source: str = "<perfil>") -> GameProfile:
    """Valida ``data`` (p. ej. un TOML ya leído) y devuelve el perfil.

    Lanza ``ProfileError`` con un mensaje que indica ``source`` y el campo.
    """
    root = _Section(data, source)
    schema = root.integer("schema", required=True)
    if schema != SCHEMA_VERSION:
        raise ProfileError(f"{source}: versión de esquema no admitida: {schema}")
    profile_id = _check_id(root.text("id", required=True), f"{source}.id")
    name = root.text("name", required=True).strip()
    if not name:
        raise ProfileError(f"{source}.name: no puede estar vacío")

    m = root.section("match")
    match = ProfileMatch(
        engine=m.text("engine") or None,
        runtimes=m.texts("runtimes"),
        titles=m.texts("titles"),
        files=tuple(_check_relative_file(f, f"{source}.match.files") for f in m.texts("files")),
    )
    m.done()
    if match.specificity == 0:
        raise ProfileError(f"{source}.match: hace falta al menos una condición")

    w = root.section("wine")
    arch = w.text("arch") or None
    if arch is not None and arch not in ARCHES:
        raise ProfileError(f"{source}.wine.arch: debe ser win32 o win64")
    environment = _check_environment(w.raw("environment"), f"{source}.wine.environment")
    w.done()

    s = root.section("saves")
    save_dirs = tuple(check_folder(p, f"{source}.saves.paths") for p in s.texts("paths"))
    config_dirs = tuple(check_folder(p, f"{source}.saves.config") for p in s.texts("config"))
    s.done()

    issues = []
    for t in root.tables("known_issues"):
        issue = KnownIssue(
            id=_check_id(t.text("id", required=True), f"{source}.known_issues.id"),
            symptom=t.text("symptom", required=True),
            solution=t.text("solution", required=True),
            output=t.texts("output"),
            harmless=t.boolean("harmless"),
        )
        t.done()
        if issue.harmless and not issue.output:
            raise ProfileError(
                f"{source}.known_issues.{issue.id}: harmless solo tiene sentido con output"
            )
        issues.append(issue)
    if len({i.id for i in issues}) != len(issues):
        raise ProfileError(f"{source}.known_issues: hay identificadores repetidos")

    c = root.section("compatibility")
    status_text = c.text("status", default=CompatibilityStatus.NOT_TESTED.value)
    try:
        status = CompatibilityStatus(status_text)
    except ValueError:
        valid = ", ".join(s.value for s in CompatibilityStatus)
        raise ProfileError(f"{source}.compatibility.status: usa uno de {valid}") from None
    notes = c.text("notes")
    c.done()

    description = root.text("description")
    root.done()
    return GameProfile(
        id=profile_id,
        name=name,
        match=match,
        description=description,
        arch=arch,
        environment=environment,
        save_dirs=save_dirs,
        config_dirs=config_dirs,
        known_issues=tuple(issues),
        status=status,
        notes=notes,
        source=source,
    )


def select_profile(
    profiles: list[GameProfile] | tuple[GameProfile, ...],
    *,
    engine: str,
    runtime: str,
    title: str | None,
    has_file: Callable[[str], bool],
) -> GameProfile | None:
    """El perfil más específico que encaja con el juego, o ``None``.

    A igual especificidad gana el que aparece antes en ``profiles``.
    """
    best: GameProfile | None = None
    for profile in profiles:
        if not profile.match.matches(
            engine=engine, runtime=runtime, title=title, has_file=has_file
        ):
            continue
        if best is None or profile.match.specificity > best.match.specificity:
            best = profile
    return best
