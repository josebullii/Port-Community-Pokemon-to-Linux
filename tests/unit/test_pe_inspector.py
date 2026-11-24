import re

import pytest

from pokemon_to_linux.infrastructure.filesystem.pe_inspector import (
    NotPEError,
    find_markers,
    inspect_pe,
    parse_pe,
)


def test_pe32_i386_gui_with_imports(make_pe):
    info = parse_pe(make_pe(imports=("KERNEL32.dll", "OPENGL32.DLL", "kernel32.dll")))

    assert info.machine == "i386"
    assert info.bits == 32
    assert info.is_dll is False
    assert info.subsystem == "gui"
    # minúsculas y sin duplicados, en orden de aparición
    assert info.imports == ("kernel32.dll", "opengl32.dll")
    assert info.imports_dll("OpenGL32.dll")


def test_pe32_plus_x86_64_console_dll(make_pe):
    info = parse_pe(make_pe(machine=0x8664, pe32_plus=True, dll=True, subsystem=3))

    assert info.machine == "x86_64"
    assert info.bits == 64
    assert info.is_dll is True
    assert info.subsystem == "console"
    assert info.imports == ()


def test_unknown_machine_is_reported_not_rejected(make_pe):
    info = parse_pe(make_pe(machine=0x1234))
    assert info.machine == "desconocida (0x1234)"


def test_inspect_pe_reads_file(tmp_path, make_pe):
    path = tmp_path / "Game.exe"
    path.write_bytes(make_pe(imports=("user32.dll",)))

    assert inspect_pe(path).imports == ("user32.dll",)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "MZ"),
        (b"hola, no soy un exe", "MZ"),
        (b"MZ" + b"\0" * 0x3A + b"\x40\0\0\0" + b"XX\0\0", "firma PE"),
    ],
)
def test_invalid_data_raises(data, message):
    with pytest.raises(NotPEError, match=message):
        parse_pe(data)


def test_truncated_pe_raises(make_pe):
    with pytest.raises(NotPEError, match="truncada"):
        parse_pe(make_pe()[:0x60])


def test_import_rva_outside_sections_is_ignored(make_pe):
    import struct

    data = bytearray(make_pe(imports=("user32.dll",)))
    # Apunta el directorio de importaciones fuera de cualquier sección.
    dirs = 0x40 + 4 + 20 + 96
    struct.pack_into("<I", data, dirs + 8, 0x7FFF0000)

    assert parse_pe(bytes(data)).imports == ()


def test_missing_file_raises(tmp_path):
    with pytest.raises(NotPEError, match="no se puede leer"):
        inspect_pe(tmp_path / "no_existe.exe")


def test_find_markers(make_pe):
    data = make_pe(payload=b"...mkxp-z...SDL2-2.0.12...")
    found = find_markers(
        data,
        {
            "mkxp_z": re.compile(rb"mkxp-z"),
            "sdl2": re.compile(rb"SDL2-(\d+\.\d+\.\d+)"),
            "nada": re.compile(rb"no-aparece"),
        },
    )

    assert found == {"mkxp_z": "mkxp-z", "sdl2": "2.0.12"}
