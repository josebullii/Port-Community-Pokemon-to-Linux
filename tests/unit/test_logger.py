import logging

import pytest

from pokemon_to_linux.infrastructure.logging.logger import (
    LOG_FILE_NAME,
    ROOT_LOGGER_NAME,
    get_logger,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _reset_app_logger():
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


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
