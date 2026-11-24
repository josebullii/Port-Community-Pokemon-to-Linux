import pytest

from pokemon_to_linux.infrastructure.filesystem.ini_reader import (
    IniReadError,
    decode_text,
    read_ini,
)

GAME_INI = (
    "[Game]\r\n"
    "Library=RGSS104E.dll\r\n"
    "Scripts=Data\\Scripts.rxdata\r\n"
    "Title={title}\r\n"
    "RTP1=\r\n"
    "RTP2=\r\n"
    "RTP3=\r\n"
)


def _write(tmp_path, content: bytes, name="Game.ini"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_reads_typical_rpg_maker_xp_ini(tmp_path):
    ini = read_ini(_write(tmp_path, GAME_INI.format(title="Pokemon Z").encode("ascii")))

    assert ini.has_section("Game")
    assert ini.get("Game", "Library") == "RGSS104E.dll"
    assert ini.get("Game", "Scripts") == "Data\\Scripts.rxdata"
    assert ini.get("Game", "Title") == "Pokemon Z"
    assert ini.get("Game", "RTP1") == ""
    assert ini.get("Game", "NoExiste", "x") == "x"


def test_sections_and_keys_are_case_insensitive(tmp_path):
    ini = read_ini(_write(tmp_path, b"[GAME]\nLIBRARY=RGSS102E.dll\n"))

    assert ini.get("game", "library") == "RGSS102E.dll"
    assert ini.get("Game", "Library") == "RGSS102E.dll"


def test_utf8_with_bom(tmp_path):
    content = "﻿" + GAME_INI.format(title="Pokémon Añil")
    ini = read_ini(_write(tmp_path, content.encode("utf-8")))

    assert ini.encoding == "utf-8-sig"
    assert ini.get("Game", "Title") == "Pokémon Añil"


def test_windows_1252(tmp_path):
    ini = read_ini(_write(tmp_path, GAME_INI.format(title="Pokémon Añil").encode("cp1252")))

    assert ini.encoding == "cp1252"
    assert ini.get("Game", "Title") == "Pokémon Añil"


def test_shift_jis(tmp_path):
    title = "ポケモン"
    ini = read_ini(_write(tmp_path, GAME_INI.format(title=title).encode("shift_jis")))

    assert ini.encoding == "shift_jis"
    assert ini.get("Game", "Title") == title


def test_shift_jis_mixed_with_kanji(tmp_path):
    title = "ポケモン 金銀"
    ini = read_ini(_write(tmp_path, GAME_INI.format(title=title).encode("shift_jis")))

    assert ini.encoding == "shift_jis"
    assert ini.get("Game", "Title") == title


@pytest.mark.parametrize("title", ["Pokémon", "Añil", "Pokémon Edición Ébano", "Ça va"])
def test_western_accents_are_not_mistaken_for_shift_jis(title):
    text, encoding = decode_text(title.encode("cp1252"))

    assert encoding == "cp1252"
    assert text == title


def test_decode_text_never_fails():
    _, encoding = decode_text(bytes(range(256)))
    assert encoding in {"cp1252", "shift_jis", "latin-1"}


def test_missing_section_header_raises(tmp_path):
    with pytest.raises(IniReadError, match="formato INI"):
        read_ini(_write(tmp_path, b"Library=RGSS104E.dll\n"))


def test_too_big_raises(tmp_path):
    path = _write(tmp_path, b"[Game]\n" + b";" * 100)
    with pytest.raises(IniReadError, match="demasiado grande"):
        read_ini(path, max_bytes=10)


def test_missing_file_raises(tmp_path):
    with pytest.raises(IniReadError, match="no se puede leer"):
        read_ini(tmp_path / "no_existe.ini")


def test_duplicate_sections_are_merged(tmp_path):
    ini = read_ini(_write(tmp_path, b"[Game]\nA=1\n[game]\nB=2\n"))

    assert ini.get("Game", "A") == "1"
    assert ini.get("Game", "B") == "2"
