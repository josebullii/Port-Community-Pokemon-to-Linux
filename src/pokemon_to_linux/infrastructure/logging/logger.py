"""Configuración del registro de la aplicación."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from pokemon_to_linux import APP_ID

ROOT_LOGGER_NAME = "pokemon_to_linux"
LOG_FILE_NAME = f"{APP_ID}.log"
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_MAX_BYTES = 1_000_000
_BACKUPS = 3


def setup_logging(log_dir: Path, level: int = logging.INFO, console: bool = True) -> Path:
    """Configura el logger raíz de la aplicación y devuelve la ruta del fichero de log.

    Es idempotente: si se llama varias veces, sustituye los handlers anteriores.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return log_file


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger hijo del de la aplicación (p. ej. ``get_logger(__name__)``)."""
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def install_excepthook() -> None:
    """Registra en el log cualquier excepción no capturada antes de salir."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    previous = sys.excepthook

    def _hook(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("Excepción no capturada", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = _hook
