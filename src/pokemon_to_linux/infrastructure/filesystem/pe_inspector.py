"""Inspección mínima de ejecutables PE (Windows) sin dependencias externas.

Solo se leen cabeceras y la tabla de importaciones; nunca se ejecuta nada.
Los ficheros se tratan como datos no confiables: todos los accesos están
acotados y cualquier inconsistencia se convierte en ``NotPEError``.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

MAX_PE_BYTES = 128 * 1024 * 1024
_MAX_IMPORTS = 1024
_MAX_NAME = 256

MACHINES = {
    0x014C: "i386",
    0x8664: "x86_64",
    0xAA64: "arm64",
    0x01C4: "arm",
}
SUBSYSTEMS = {2: "gui", 3: "console"}

_PE32 = 0x10B
_PE32_PLUS = 0x20B
_IMAGE_FILE_DLL = 0x2000


class NotPEError(ValueError):
    """El fichero no es un PE válido o está dañado."""


@dataclass(frozen=True, slots=True)
class PEInfo:
    machine: str
    bits: int
    is_dll: bool
    subsystem: str
    imports: tuple[str, ...]

    def imports_dll(self, name: str) -> bool:
        return name.lower() in self.imports


def read_binary(path: Path, max_bytes: int = MAX_PE_BYTES) -> bytes:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise NotPEError(f"{path.name}: demasiado grande ({size} bytes)")
        return path.read_bytes()
    except OSError as exc:
        raise NotPEError(f"{path.name}: no se puede leer ({exc.strerror or exc})") from exc


def inspect_pe(path: Path) -> PEInfo:
    return parse_pe(read_binary(path))


def parse_pe(data: bytes) -> PEInfo:
    try:
        return _parse(data)
    except (struct.error, IndexError) as exc:
        raise NotPEError("cabecera PE truncada o dañada") from exc


def _parse(data: bytes) -> PEInfo:
    if data[:2] != b"MZ":
        raise NotPEError("no empieza por la firma MZ")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise NotPEError("no tiene la firma PE")

    coff = pe_offset + 4
    machine_id, n_sections, _, _, _, opt_size, characteristics = struct.unpack_from(
        "<HHIIIHH", data, coff
    )
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == _PE32:
        bits, dirs_offset = 32, opt + 96
    elif magic == _PE32_PLUS:
        bits, dirs_offset = 64, opt + 112
    else:
        raise NotPEError(f"cabecera opcional desconocida (0x{magic:x})")

    subsystem_id = struct.unpack_from("<H", data, opt + 68)[0]
    n_dirs = struct.unpack_from("<I", data, dirs_offset - 4)[0]

    sections = []
    table = opt + opt_size
    for i in range(n_sections):
        _, vsize, va, raw_size, raw_ptr = struct.unpack_from("<8sIIII", data, table + 40 * i)
        sections.append((va, max(vsize, raw_size), raw_ptr))

    imports: tuple[str, ...] = ()
    if n_dirs > 1:
        import_rva = struct.unpack_from("<I", data, dirs_offset + 8)[0]
        if import_rva:
            imports = _read_imports(data, sections, import_rva)

    return PEInfo(
        machine=MACHINES.get(machine_id, f"desconocida (0x{machine_id:04x})"),
        bits=bits,
        is_dll=bool(characteristics & _IMAGE_FILE_DLL),
        subsystem=SUBSYSTEMS.get(subsystem_id, f"otro ({subsystem_id})"),
        imports=imports,
    )


def _rva_to_offset(sections: list[tuple[int, int, int]], rva: int) -> int | None:
    for va, size, raw_ptr in sections:
        if va <= rva < va + size:
            return rva - va + raw_ptr
    return None


def _read_imports(data: bytes, sections: list[tuple[int, int, int]], rva: int) -> tuple[str, ...]:
    offset = _rva_to_offset(sections, rva)
    names: list[str] = []
    seen: set[str] = set()
    for _ in range(_MAX_IMPORTS):
        if offset is None or offset + 20 > len(data):
            break
        descriptor = struct.unpack_from("<IIIII", data, offset)
        if not any(descriptor):
            break
        name_offset = _rva_to_offset(sections, descriptor[3])
        if name_offset is not None and name_offset < len(data):
            end = data.find(b"\0", name_offset, name_offset + _MAX_NAME)
            if end != -1:
                name = data[name_offset:end].decode("ascii", errors="replace").lower()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        offset += 20
    return tuple(names)


def find_markers(data: bytes, patterns: dict[str, re.Pattern[bytes]]) -> dict[str, str]:
    """Busca patrones binarios; devuelve {nombre: primer grupo o coincidencia}."""
    found: dict[str, str] = {}
    for name, pattern in patterns.items():
        match = pattern.search(data)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            found[name] = value.decode("ascii", errors="replace")
    return found
