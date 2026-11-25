import logging
import os
from pathlib import Path

import pytest

from pokemon_to_linux.infrastructure.logging.logger import ROOT_LOGGER_NAME
from pokemon_to_linux.infrastructure.wine.prefix_manager import TEST_EXIT_CODE
from pokemon_to_linux.infrastructure.wine.wine_manager import CommandResult

# Permite ejecutar las pruebas de Qt sin pantalla (CI, SSH, consola).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """QApplication compartida por todas las pruebas que usan widgets."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")  # noqa: N806
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def wait_until(predicate, timeout=5.0):
    """Procesa eventos de Qt hasta que ``predicate()`` sea cierto (tareas en segundo plano)."""
    import time

    from PySide6.QtCore import QCoreApplication, QEventLoop

    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("no se cumplió la condición a tiempo")
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


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


def build_game_ini(
    *,
    library: str = "RGSS104E.dll",
    scripts: str = "Data\\Scripts.rxdata",
    title: str = "Juego de prueba",
    rtp1: str = "",
) -> bytes:
    return (
        f"[Game]\r\nLibrary={library}\r\nScripts={scripts}\r\nTitle={title}\r\n"
        f"RTP1={rtp1}\r\nRTP2=\r\nRTP3=\r\n"
    ).encode("cp1252")


EXE_KINDS = {
    # Reproductor RGSS clásico: sin marcadores especiales.
    "rgss": lambda: build_pe(imports=("kernel32.dll", "user32.dll", "gdi32.dll")),
    # mkxp-z como en Pokémon Z: usa OpenGL y lleva SDL2 enlazado.
    "mkxp-z": lambda: build_pe(
        imports=("kernel32.dll", "opengl32.dll"), payload=b"\0mkxp-z\0SDL2-2.0.12\0"
    ),
    "garbage": lambda: b"esto no es un ejecutable",
    # Ejecutable real de 32 bits que termina con código 7 (el "juego de prueba").
    "runnable": lambda: _runnable_exe(),
}

RUNNABLE_EXIT_CODE = 7


def _runnable_exe() -> bytes:
    from pokemon_to_linux.infrastructure.wine.test_program import build_exit_program

    return build_exit_program(RUNNABLE_EXIT_CODE, bits=32)


@pytest.fixture
def make_game(tmp_path):
    """Fábrica de carpetas de juego falsas (sin recursos con copyright).

    Por defecto crea un juego RPG Maker XP clásico: Game.exe + Game.ini +
    RGSS104E.dll + Data/*.rxdata + Graphics/ + Audio/.
    """
    counter = iter(range(1000))

    def factory(
        *,
        ini: bytes | None = None,
        no_ini: bool = False,
        exe: str | None = "rgss",
        exe_name: str = "Game.exe",
        dlls: tuple[str, ...] = ("RGSS104E.dll",),
        data_dir: str = "Data",
        data: tuple[str, ...] = ("Scripts.rxdata", "Map001.rxdata"),
        resources: bool = True,
        extra: dict[str, bytes] | None = None,
    ):
        root = tmp_path / f"juego{next(counter)}"
        root.mkdir()
        if not no_ini:
            (root / "Game.ini").write_bytes(ini if ini is not None else build_game_ini())
        if exe is not None:
            (root / exe_name).write_bytes(EXE_KINDS[exe]())
        for dll in dlls:
            (root / dll).write_bytes(build_pe(dll=True, subsystem=3))
        if data:
            (root / data_dir).mkdir()
            for name in data:
                (root / data_dir / name).write_bytes(b"\x04\x08")  # cabecera Marshal
        if resources:
            (root / "Graphics" / "Titles").mkdir(parents=True)
            (root / "Audio" / "BGM").mkdir(parents=True)
        for rel, content in (extra or {}).items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return root

    return factory


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


class FakeWine:  # noqa: D101
    """Simula wine/wineserver: wineboot crea system.reg con la arquitectura pedida."""

    def __init__(self, *, wineboot_code=0, created_arch=None, program_code=TEST_EXIT_CODE):
        self.calls = []
        self.wineboot_code = wineboot_code
        self.created_arch = created_arch
        self.program_code = program_code

    def __call__(self, args, env, timeout, cwd):
        self.calls.append((list(args), dict(env)))
        prefix = Path(env["WINEPREFIX"])
        if args[1:] == ["wineboot", "--init"]:
            if self.wineboot_code == 0:
                prefix.mkdir(parents=True, exist_ok=True)
                arch = self.created_arch or env.get("WINEARCH", "win64")
                (prefix / "system.reg").write_text(
                    "WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n\n"
                    f"#arch={arch}\n"
                )
            return CommandResult(self.wineboot_code, "err:wineboot: algo falló\n")
        if args[0].endswith(".exe") or (len(args) > 1 and args[1].endswith(".exe")):
            return CommandResult(self.program_code, "")
        return CommandResult(0, "")

    def commands(self):
        return [args[1:] if "wineserver" not in args[0] else ["wineserver", *args[1:]]
                for args, _ in self.calls]  # fmt: skip
