"""Pokémon to Linux: lanzador y gestor de compatibilidad para fangames de Pokémon."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "Pokémon to Linux"
APP_ID = "pokemon-to-linux"

try:
    __version__ = version(APP_ID)
except PackageNotFoundError:  # ejecutado desde el código fuente sin instalar
    __version__ = "0.0.0+local"

__all__ = ["APP_ID", "APP_NAME", "__version__"]
