"""Rutas de la aplicación según la especificación XDG Base Directory.

https://specifications.freedesktop.org/basedir-spec/latest/
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_to_linux import APP_ID

# (variable XDG, ruta por defecto relativa a $HOME)
_XDG_DEFAULTS: dict[str, tuple[str, str]] = {
    "data": ("XDG_DATA_HOME", ".local/share"),
    "config": ("XDG_CONFIG_HOME", ".config"),
    "cache": ("XDG_CACHE_HOME", ".cache"),
    "state": ("XDG_STATE_HOME", ".local/state"),
}


def _xdg_base(kind: str, env: Mapping[str, str], home: Path) -> Path:
    var, default = _XDG_DEFAULTS[kind]
    value = env.get(var, "").strip()
    # La especificación exige ignorar rutas relativas.
    if value and Path(value).is_absolute():
        return Path(value)
    return home / default


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Directorios donde la aplicación guarda sus datos."""

    data_dir: Path
    config_dir: Path
    cache_dir: Path
    state_dir: Path

    @property
    def prefixes_dir(self) -> Path:
        """Prefijos Wine, uno por juego."""
        return self.data_dir / "prefixes"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "library.sqlite3"

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "logs"

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> AppPaths:
        env = os.environ if env is None else env
        home = Path.home() if home is None else home
        return cls(
            data_dir=_xdg_base("data", env, home) / APP_ID,
            config_dir=_xdg_base("config", env, home) / APP_ID,
            cache_dir=_xdg_base("cache", env, home) / APP_ID,
            state_dir=_xdg_base("state", env, home) / APP_ID,
        )

    def ensure(self) -> None:
        """Crea los directorios si no existen."""
        for path in (
            self.data_dir,
            self.config_dir,
            self.cache_dir,
            self.state_dir,
            self.prefixes_dir,
            self.log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
