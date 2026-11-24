import logging
import sys

import pytest

from pokemon_to_linux.infrastructure.logging.logger import (
    LOG_FILE_NAME,
    ROOT_LOGGER_NAME,
    get_logger,
    install_excepthook,
    setup_logging,
)


def _flush():
    for handler in logging.getLogger(ROOT_LOGGER_NAME).handlers:
        handler.flush()


def test_setup_creates_log_file_and_writes(tmp_path):
    log_file = setup_logging(tmp_path / "logs", console=False)

    get_logger("prueba").info("hola mundo")
    _flush()

    assert log_file == tmp_path / "logs" / LOG_FILE_NAME
    content = log_file.read_text(encoding="utf-8")
    assert "hola mundo" in content
    assert f"{ROOT_LOGGER_NAME}.prueba" in content


def test_setup_is_idempotent(tmp_path):
    setup_logging(tmp_path, console=False)
    setup_logging(tmp_path, console=False)

    assert len(logging.getLogger(ROOT_LOGGER_NAME).handlers) == 1


def test_level_is_respected(tmp_path):
    log_file = setup_logging(tmp_path, level=logging.WARNING, console=False)

    log = get_logger("nivel")
    log.info("no debe aparecer")
    log.warning("sí debe aparecer")
    _flush()

    content = log_file.read_text(encoding="utf-8")
    assert "no debe aparecer" not in content
    assert "sí debe aparecer" in content


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("modulo", f"{ROOT_LOGGER_NAME}.modulo"),
        (ROOT_LOGGER_NAME, ROOT_LOGGER_NAME),
        (f"{ROOT_LOGGER_NAME}.ui", f"{ROOT_LOGGER_NAME}.ui"),
    ],
)
def test_get_logger_names(name, expected):
    assert get_logger(name).name == expected


@pytest.fixture
def previous_hook(monkeypatch):
    """Sustituye sys.excepthook por uno que registra llamadas (y se restaura al final)."""
    calls = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: calls.append(args))
    return calls


def test_excepthook_logs_uncaught_exception(tmp_path, previous_hook):
    log_file = setup_logging(tmp_path, console=False)
    install_excepthook()

    try:
        raise ValueError("fallo de prueba")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    _flush()

    content = log_file.read_text(encoding="utf-8")
    assert "Excepción no capturada" in content
    assert "ValueError: fallo de prueba" in content
    assert len(previous_hook) == 1  # el hook anterior se sigue llamando


def test_excepthook_ignores_keyboard_interrupt(tmp_path, previous_hook):
    log_file = setup_logging(tmp_path, console=False)
    install_excepthook()

    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    _flush()

    assert "Excepción no capturada" not in log_file.read_text(encoding="utf-8")
    assert len(previous_hook) == 1
