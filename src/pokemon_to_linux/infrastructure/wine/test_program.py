"""Programa de prueba para Windows generado byte a byte.

Es un ejecutable PE mínimo y real que solo llama a
``kernel32!ExitProcess(código)``. Sirve para:

- comprobar que un Wine concreto ejecuta programas de 32 y/o 64 bits
  (sin depender de lo que diga el empaquetado de cada distribución);
- probar el lanzador de extremo a extremo sin juegos con copyright.

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
_ILT = 0x080
_IAT = 0x090
_HINT_NAME = 0x0A0  # WORD hint + "ExitProcess\0"
_DLL_NAME = 0x0B0

_SUBSYSTEM_CONSOLE = 3


def build_exit_program(exit_code: int, *, bits: int = 32) -> bytes:
    """Devuelve un ``.exe`` que termina con ``exit_code`` (0–255 para portabilidad)."""
    if not 0 <= exit_code <= 255:
        raise ValueError("exit_code debe estar entre 0 y 255")
    if bits not in (32, 64):
        raise ValueError("bits debe ser 32 o 64")
    pe32_plus = bits == 64
    image_base = 0x140000000 if pe32_plus else 0x400000
    rva = _SECTION_RVA

    # --- Sección .text: código + tabla de importaciones -------------------
    section = bytearray(_SECTION_SIZE)
    iat_rva = rva + _IAT
    if pe32_plus:
        # sub rsp,0x28 ; mov ecx,code ; call [rip+rel32] ; int3
        call_at = _CODE + 4 + 5
        rel = (iat_rva) - (rva + call_at + 6)
        code = (
            b"\x48\x83\xec\x28"
            + b"\xb9"
            + struct.pack("<I", exit_code)
            + b"\xff\x15"
            + struct.pack("<i", rel)
            + b"\xcc"
        )
        thunk = "<Q"
    else:
        # push code ; call [abs32] ; int3
        code = (
            b"\x68"
            + struct.pack("<I", exit_code)
            + b"\xff\x15"
            + struct.pack("<I", image_base + iat_rva)
            + b"\xcc"
        )
        thunk = "<I"
    section[_CODE : _CODE + len(code)] = code

    struct.pack_into("<IIIII", section, _IMPORT_DESCRIPTORS, rva + _ILT, 0, 0, rva + _DLL_NAME,
                     iat_rva)  # fmt: skip
    struct.pack_into(thunk, section, _ILT, rva + _HINT_NAME)
    struct.pack_into(thunk, section, _IAT, rva + _HINT_NAME)
    section[_HINT_NAME + 2 : _HINT_NAME + 2 + 12] = b"ExitProcess\0"
    section[_DLL_NAME : _DLL_NAME + 13] = b"KERNEL32.dll\0"

    # --- Cabeceras ---------------------------------------------------------
    opt_size = 240 if pe32_plus else 224
    opt = bytearray(opt_size)
    struct.pack_into("<HBB", opt, 0, 0x20B if pe32_plus else 0x10B, 14, 0)
    struct.pack_into("<III", opt, 4, _SECTION_SIZE, 0, 0)  # SizeOfCode / Init / Uninit
    struct.pack_into("<II", opt, 16, rva + _CODE, rva)  # EntryPoint, BaseOfCode
    if pe32_plus:
        struct.pack_into("<Q", opt, 24, image_base)
        fields = 32
    else:
        struct.pack_into("<II", opt, 24, rva, image_base)  # BaseOfData, ImageBase
        fields = 32
    struct.pack_into("<II", opt, fields, _SECTION_RVA, _FILE_ALIGN)
    struct.pack_into("<HHHHHH", opt, fields + 8, 6, 0, 0, 0, 6, 0)  # versiones SO/imagen/subsistema
    struct.pack_into("<IIII", opt, fields + 20, 0, _IMAGE_SIZE, _FILE_ALIGN, 0)
    struct.pack_into("<HH", opt, fields + 36, _SUBSYSTEM_CONSOLE, 0)  # sin ASLR: base fija
    if pe32_plus:
        struct.pack_into("<QQQQII", opt, fields + 40, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
        dirs = 112
    else:
        struct.pack_into("<IIIIII", opt, fields + 40, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
        dirs = 96
    struct.pack_into("<II", opt, dirs + 8 * 1, rva + _IMPORT_DESCRIPTORS, 40)  # Import
    struct.pack_into("<II", opt, dirs + 8 * 12, iat_rva, 16)  # IAT

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


def write_exit_program(path: Path, exit_code: int, *, bits: int = 32) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_exit_program(exit_code, bits=bits))
    return path
