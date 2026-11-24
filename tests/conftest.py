import logging
import os

import pytest

from pokemon_to_linux.infrastructure.logging.logger import ROOT_LOGGER_NAME

# Permite ejecutar las pruebas de Qt sin pantalla (CI, SSH, consola).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """QApplication compartida por todas las pruebas que usan widgets."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")  # noqa: N806
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_app_logger():
    """Cierra los handlers del logger de la app tras cada prueba (evita ficheros abiertos)."""
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def build_pe(
    *,
    machine: int = 0x014C,
    pe32_plus: bool = False,
    dll: bool = False,
    subsystem: int = 2,
    imports: tuple[str, ...] = (),
    payload: bytes = b"",
) -> bytes:
    """Construye un PE mínimo pero válido (cabeceras + sección .idata + payload).

    Sirve para probar el inspector y el detector sin incluir binarios reales.
    """
    import struct

    section_va, section_raw = 0x1000, 0x200

    # Sección .idata: descriptores (20 bytes c/u + uno nulo) seguidos de nombres.
    descriptors_size = 20 * (len(imports) + 1)
    names_blob = b""
    descriptors = b""
    for name in imports:
        name_rva = section_va + descriptors_size + len(names_blob)
        descriptors += struct.pack("<IIIII", 0, 0, 0, name_rva, 0)
        names_blob += name.encode("ascii") + b"\0"
    section = descriptors + b"\0" * 20 + names_blob
    section += b"\0" * (-len(section) % 0x200)

    opt_size = 240 if pe32_plus else 224
    optional = bytearray(opt_size)
    struct.pack_into("<H", optional, 0, 0x20B if pe32_plus else 0x10B)
    struct.pack_into("<H", optional, 68, subsystem)
    dirs = 112 if pe32_plus else 96
    struct.pack_into("<I", optional, dirs - 4, 16)  # NumberOfRvaAndSizes
    if imports:
        struct.pack_into("<II", optional, dirs + 8, section_va, descriptors_size)

    characteristics = 0x0102 | (0x2000 if dll else 0)
    coff = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, opt_size, characteristics)
    section_header = struct.pack(
        "<8sIIIIIIHHI",
        b".idata",
        len(section),
        section_va,
        len(section),
        section_raw,
        0,
        0,
        0,
        0,
        0,
    )

    dos = bytearray(0x40)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    headers = bytes(dos) + b"PE\0\0" + coff + bytes(optional) + section_header
    headers += b"\0" * (section_raw - len(headers))
    return headers + section + payload


@pytest.fixture
def make_pe():
    return build_pe


@pytest.fixture
def xdg_tmp(tmp_path, monkeypatch):
    """Redirige todas las rutas XDG a un directorio temporal."""
    for var, sub in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
    ):
        monkeypatch.setenv(var, str(tmp_path / sub))
    return tmp_path
