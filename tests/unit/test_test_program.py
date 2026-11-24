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


def test_sleep_and_exit_code_are_embedded_in_32_bit_code():
    data = build_exit_program(42, bits=32, sleep_ms=1500)
    # La sección empieza en el offset 0x200: push ms ; call [Sleep] ; push code ; call […]
    assert data[0x200] == 0x68
    assert struct.unpack_from("<I", data, 0x201)[0] == 1500
    assert data[0x205:0x207] == b"\xff\x15"
    assert data[0x20B] == 0x68
    assert struct.unpack_from("<I", data, 0x20C)[0] == 42


def test_sleep_and_exit_code_are_embedded_in_64_bit_code():
    data = build_exit_program(7, bits=64, sleep_ms=250)
    # sub rsp,0x28 ; mov ecx,ms ; call [rip+…] ; mov ecx,code ; call [rip+…]
    assert data[0x200:0x204] == b"\x48\x83\xec\x28"
    assert data[0x204] == 0xB9
    assert struct.unpack_from("<I", data, 0x205)[0] == 250
    assert data[0x209:0x20B] == b"\xff\x15"
    assert data[0x20F] == 0xB9
    assert struct.unpack_from("<I", data, 0x210)[0] == 7


@pytest.mark.parametrize("bits", [32, 64])
def test_imports_sleep_and_exit_process(bits):
    data = build_exit_program(0, bits=bits)
    assert b"Sleep\0" in data
    assert b"ExitProcess\0" in data


def test_invalid_sleep():
    with pytest.raises(ValueError, match="sleep_ms"):
        build_exit_program(0, sleep_ms=-1)
    with pytest.raises(ValueError, match="sleep_ms"):
        build_exit_program(0, sleep_ms=0xFFFFFFFF)  # INFINITE no se permite


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
