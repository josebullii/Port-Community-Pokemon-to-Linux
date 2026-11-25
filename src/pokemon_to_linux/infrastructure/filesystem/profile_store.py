"""Carga de perfiles de compatibilidad desde ficheros TOML.

- **Integrados**: ``pokemon_to_linux/profiles/*.toml``, dentro del paquete.
  Si uno no es válido es un fallo del programa y se lanza ``ProfileError``.
- **Del usuario**: ``~/.config/pokemon-to-linux/profiles/*.toml``. Uno con
  el mismo ``id`` que un integrado lo sustituye. Los que no son válidos se
  ignoran y el error se devuelve en ``ProfileSet.errors``: un perfil roto no
  debe impedir lanzar los demás juegos.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from pokemon_to_linux.domain.profile import GameProfile, ProfileError, parse_profile
from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

MAX_PROFILE_SIZE = 64 * 1024


def builtin_profiles_dir() -> Traversable:
    return files("pokemon_to_linux") / "profiles"


@dataclass(frozen=True, slots=True)
class ProfileSet:
    profiles: tuple[GameProfile, ...]
    """Los del usuario primero: en un empate de especificidad, ganan ellos."""
    errors: tuple[str, ...] = ()

    def get(self, profile_id: str) -> GameProfile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)


def _read(entry: Traversable | Path, source: str) -> GameProfile:
    try:
        raw = entry.read_bytes()
    except OSError as exc:
        raise ProfileError(f"{source}: no se puede leer ({exc})") from exc
    if len(raw) > MAX_PROFILE_SIZE:
        raise ProfileError(f"{source}: ocupa demasiado (máximo {MAX_PROFILE_SIZE // 1024} KB)")
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"{source}: TOML no válido ({exc})") from exc
    return parse_profile(data, source)


def _toml_entries(folder: Traversable | Path) -> list[Traversable | Path]:
    if not folder.is_dir():
        return []
    return sorted(
        (e for e in folder.iterdir() if e.name.endswith(".toml") and e.is_file()),
        key=lambda e: e.name,
    )


def _unique(profiles: Iterable[GameProfile], kind: str) -> dict[str, GameProfile]:
    result: dict[str, GameProfile] = {}
    for profile in profiles:
        if profile.id in result:
            raise ProfileError(
                f"{profile.source}: el id {profile.id!r} ya lo usa "
                f"{result[profile.id].source} ({kind})"
            )
        result[profile.id] = profile
    return result


def load_profiles(
    user_dir: Path | None = None,
    *,
    builtin_dir: Traversable | Path | None = None,
) -> ProfileSet:
    builtin_dir = builtin_profiles_dir() if builtin_dir is None else builtin_dir
    builtin = _unique(
        (_read(e, f"perfiles integrados/{e.name}") for e in _toml_entries(builtin_dir)),
        "integrado",
    )

    user: dict[str, GameProfile] = {}
    errors: list[str] = []
    if user_dir is not None:
        for entry in _toml_entries(user_dir):
            try:
                profile = _read(entry, str(entry))
            except ProfileError as exc:
                errors.append(str(exc))
                log.warning("Perfil ignorado: %s", exc)
                continue
            if profile.id in user:
                errors.append(f"{entry}: el id {profile.id!r} está repetido; se ignora")
                continue
            if profile.id in builtin:
                log.info("El perfil %s del usuario sustituye al integrado", profile.id)
            user[profile.id] = profile

    profiles = [*user.values(), *(p for pid, p in builtin.items() if pid not in user)]
    return ProfileSet(tuple(profiles), tuple(errors))
