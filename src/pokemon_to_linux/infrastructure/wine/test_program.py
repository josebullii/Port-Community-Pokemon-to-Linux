"""Programa de prueba para Windows generado byte a byte.

Es un ejecutable PE mínimo y real que llama a ``kernel32!Sleep(ms)`` y
después a ``kernel32!ExitProcess(código)``. Sirve para:

- comprobar que un Wine concreto ejecuta programas de 32 y/o 64 bits
  (sin depender de lo que diga el empaquetado de cada distribución);
- probar el lanzador de extremo a extremo sin juegos con copyright,
  incluido detener un programa que sigue en marcha (``sleep_ms`` grande).

No hace falta compilador ni guardar binarios en el repositorio: el
fichero se genera cuando se necesita.
"""

from __future__ import annotations

import struct
from pathlib import Path

_FILE_ALIGN = 0x200
_SECTION_RVA = 0x1000
_SECTION_SIZE = 0x200
_IMAGE_SIZE = 0x2000

# Desplazamientos dentro de la sección .text
_CODE = 0x000
_IMPORT_DESCRIPTORS = 0x040  # descriptor de kernel32 + descriptor nulo
_ILT = 0x080  # [Sleep, ExitProcess, 0]
_IAT = 0x0A0  # [Sleep, ExitProcess, 0]
_HINT_SLEEP = 0x0C0  # WORD hint + "Sleep\0"
_HINT_EXIT = 0x0D0  # WORD hint + "ExitProcess\0"
_DLL_NAME = 0x0E0

_SUBSYSTEM_CONSOLE = 3
MAX_SLEEP_MS = 0xFFFFFFFE  # 0xFFFFFFFF sería INFINITE


def build_exit_program(exit_code: int, *, bits: int = 32, sleep_ms: int = 0) -> bytes:
    """``.exe`` que espera ``sleep_ms`` y termina con ``exit_code`` (0–255)."""
    if not 0 <= exit_code <= 255:
        raise ValueError("exit_code debe estar entre 0 y 255")
    if bits not in (32, 64):
        raise ValueError("bits debe ser 32 o 64")
    if not 0 <= sleep_ms <= MAX_SLEEP_MS:
        raise ValueError("sleep_ms fuera de rango")
    pe32_plus = bits == 64
    image_base = 0x140000000 if pe32_plus else 0x400000
    rva = _SECTION_RVA
    slot = 8 if pe32_plus else 4
    iat_sleep, iat_exit = rva + _IAT, rva + _IAT + slot

    # --- Sección .text: código + tabla de importaciones -------------------
    section = bytearray(_SECTION_SIZE)
    if pe32_plus:
        # sub rsp,0x28 ; mov ecx,ms ; call [rip+a] ; mov ecx,code ; call [rip+b] ; int3
        def call(at: int, target: int) -> bytes:
            return b"\xff\x15" + struct.pack("<i", target - (rva + at + 6))

        code = b"\x48\x83\xec\x28" + b"\xb9" + struct.pack("<I", sleep_ms)
        code += call(len(code), iat_sleep)
        code += b"\xb9" + struct.pack("<I", exit_code)
        code += call(len(code), iat_exit) + b"\xcc"
        thunk = "<Q"
    else:
        # push ms ; call [Sleep] ; push code ; call [ExitProcess] ; int3
        code = (
            b"\x68" + struct.pack("<I", sleep_ms)
            + b"\xff\x15" + struct.pack("<I", image_base + iat_sleep)
            + b"\x68" + struct.pack("<I", exit_code)
            + b"\xff\x15" + struct.pack("<I", image_base + iat_exit)
            + b"\xcc"
        )  # fmt: skip
        thunk = "<I"
    section[_CODE : _CODE + len(code)] = code

    struct.pack_into("<IIIII", section, _IMPORT_DESCRIPTORS, rva + _ILT, 0, 0, rva + _DLL_NAME,
                     iat_sleep)  # fmt: skip
    for table in (_ILT, _IAT):
        struct.pack_into(thunk, section, table, rva + _HINT_SLEEP)
        struct.pack_into(thunk, section, table + slot, rva + _HINT_EXIT)
    section[_HINT_SLEEP + 2 : _HINT_SLEEP + 2 + 6] = b"Sleep\0"
    section[_HINT_EXIT + 2 : _HINT_EXIT + 2 + 12] = b"ExitProcess\0"
    section[_DLL_NAME : _DLL_NAME + 13] = b"KERNEL32.dll\0"

    # --- Cabeceras ---------------------------------------------------------
    opt_size = 240 if pe32_plus else 224
    opt = bytearray(opt_size)
    struct.pack_into("<HBB", opt, 0, 0x20B if pe32_plus else 0x10B, 14, 0)
    struct.pack_into("<III", opt, 4, _SECTION_SIZE, 0, 0)  # SizeOfCode / Init / Uninit
    struct.pack_into("<II", opt, 16, rva + _CODE, rva)  # EntryPoint, BaseOfCode
    if pe32_plus:
        struct.pack_into("<Q", opt, 24, image_base)
    else:
        struct.pack_into("<II", opt, 24, rva, image_base)  # BaseOfData, ImageBase
    struct.pack_into("<II", opt, 32, _SECTION_RVA, _FILE_ALIGN)
    struct.pack_into("<HHHHHH", opt, 40, 6, 0, 0, 0, 6, 0)  # versiones SO/imagen/subsistema
    struct.pack_into("<IIII", opt, 52, 0, _IMAGE_SIZE, _FILE_ALIGN, 0)
    struct.pack_into("<HH", opt, 68, _SUBSYSTEM_CONSOLE, 0)  # sin ASLR: base fija
    if pe32_plus:
        struct.pack_into("<QQQQII", opt, 72, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
        dirs = 112
    else:
        struct.pack_into("<IIIIII", opt, 72, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
        dirs = 96
    struct.pack_into("<II", opt, dirs + 8 * 1, rva + _IMPORT_DESCRIPTORS, 40)  # Import
    struct.pack_into("<II", opt, dirs + 8 * 12, iat_sleep, 3 * slot)  # IAT

    machine = 0x8664 if pe32_plus else 0x014C
    # RELOCS_STRIPPED | EXECUTABLE_IMAGE | (32BIT_MACHINE o LARGE_ADDRESS_AWARE)
    characteristics = 0x0001 | 0x0002 | (0x0020 if pe32_plus else 0x0100)
    coff = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, opt_size, characteristics)
    section_header = struct.pack(
        "<8sIIIIIIHHI",
        b".text",
        _SECTION_SIZE,
        _SECTION_RVA,
        _SECTION_SIZE,
        _FILE_ALIGN,
        0,
        0,
        0,
        0,
        0xE0000020,  # código | ejecutable | lectura | escritura (la IAT se rellena)
    )

    dos = bytearray(0x40)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    headers = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + section_header
    headers += b"\0" * (_FILE_ALIGN - len(headers))
    return headers + bytes(section)


def write_exit_program(path: Path, exit_code: int, *, bits: int = 32, sleep_ms: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_exit_program(exit_code, bits=bits, sleep_ms=sleep_ms))
    return path
