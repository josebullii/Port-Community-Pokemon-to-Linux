"""Lectura tolerante de ficheros INI de juegos para Windows (p. ej. ``Game.ini``).

Los juegos de RPG Maker se distribuyen con INI en codificaciones heredadas
(Windows-1252, Shift-JIS…) y con mayúsculas/minúsculas inconsistentes, así que:

- se detecta la codificación (ver ``decode_text``) y se registra la usada;
- secciones y claves se normalizan a minúsculas;
- no hay interpolación ni se ejecuta nada: es solo lectura de datos.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_INI_BYTES = 64 * 1024

# Hiragana y katakana (U+3041–U+30FA). El texto japonés casi siempre los
# contiene; el texto occidental mal leído como Shift-JIS casi nunca.
_KANA = re.compile("[ぁ-ヺ]")


class IniReadError(ValueError):
    """El fichero no se puede leer como INI."""


@dataclass(frozen=True, slots=True)
class IniFile:
    path: Path
    encoding: str
    sections: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, section: str, key: str, default: str | None = None) -> str | None:
        return self.sections.get(section.lower(), {}).get(key.lower(), default)

    def has_section(self, section: str) -> bool:
        return section.lower() in self.sections


def _try_decode(raw: bytes, encoding: str) -> str | None:
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        return None


def decode_text(raw: bytes) -> tuple[str, str]:
    """Decodifica bytes de un INI heredado; devuelve (texto, codificación).

    1. UTF-8 (con o sin BOM) si es válido.
    2. Shift-JIS si es válido *y* el resultado contiene kana: muchos bytes
       Shift-JIS también son cp1252 válido, así que probar en orden no basta.
    3. Windows-1252.
    4. latin-1, que nunca falla.

    Limitación conocida: un título japonés solo con kanji (sin kana) se leerá
    como cp1252.
    """
    if (text := _try_decode(raw, "utf-8-sig")) is not None:
        return text, "utf-8-sig"
    if (text := _try_decode(raw, "shift_jis")) is not None and _KANA.search(text):
        return text, "shift_jis"
    if (text := _try_decode(raw, "cp1252")) is not None:
        return text, "cp1252"
    return raw.decode("latin-1"), "latin-1"


def read_ini(path: Path, max_bytes: int = MAX_INI_BYTES) -> IniFile:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise IniReadError(f"{path.name}: demasiado grande ({size} bytes)")
        raw = path.read_bytes()
    except OSError as exc:
        raise IniReadError(f"{path.name}: no se puede leer ({exc.strerror or exc})") from exc

    text, encoding = decode_text(raw)

    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        allow_no_value=True,
        delimiters=("=",),
        comment_prefixes=(";", "#"),
    )
    try:
        parser.read_string(text, source=str(path))
    except configparser.Error as exc:
        raise IniReadError(f"{path.name}: formato INI no válido ({exc.message})") from exc

    sections: dict[str, dict[str, str]] = {}
    for name in parser.sections():
        target = sections.setdefault(name.strip().lower(), {})
        for key, value in parser.items(name):
            target[key.strip().lower()] = (value or "").strip()

    return IniFile(path=path, encoding=encoding, sections=sections)
