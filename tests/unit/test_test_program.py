import struct

import pytest

from pokemon_to_linux.infrastructure.filesystem.pe_inspector import parse_pe
from pokemon_to_linux.infrastructure.wine.test_program import (
    build_exit_program,
    write_exit_program,
)


@pytest.mark.parametrize(("bits", "machine"), [(32, "i386"), (64, "x86_64")])
def test_program_is_a_valid_console_exe(bits, machine):
    info = parse_pe(build_exit_program(42, bits=bits))

    assert info.machine == machine
    assert info.bits == bits
    assert info.is_dll is False
    assert info.subsystem == "console"
    assert info.imports == ("kernel32.dll",)


def test_exit_code_is_embedded_in_32_bit_code():
    data = build_exit_program(42, bits=32)
    # push imm32 al inicio de la sección (offset 0x200 en el fichero)
    assert data[0x200] == 0x68
    assert struct.unpack_from("<I", data, 0x201)[0] == 42


def test_exit_code_is_embedded_in_64_bit_code():
    data = build_exit_program(7, bits=64)
    # sub rsp,0x28 ; mov ecx,imm32
    assert data[0x200:0x204] == b"\x48\x83\xec\x28"
    assert data[0x204] == 0xB9
    assert struct.unpack_from("<I", data, 0x205)[0] == 7


def test_programs_differ_only_by_exit_code():
    a, b = build_exit_program(1), build_exit_program(2)
    assert len(a) == len(b)
    assert sum(x != y for x, y in zip(a, b, strict=True)) == 1


@pytest.mark.parametrize("code", [-1, 256])
def test_invalid_exit_code(code):
    with pytest.raises(ValueError, match="exit_code"):
        build_exit_program(code)


def test_invalid_bits():
    with pytest.raises(ValueError, match="bits"):
        build_exit_program(0, bits=16)


def test_write_exit_program(tmp_path):
    path = write_exit_program(tmp_path / "sub" / "prueba.exe", 3)
    assert path.read_bytes() == build_exit_program(3)
