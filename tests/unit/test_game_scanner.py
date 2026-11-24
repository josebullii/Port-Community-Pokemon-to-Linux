import os
import sys
from pathlib import Path

import pytest

from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScanError, GameScanner


@pytest.fixture
def game_dir(tmp_path):
    root = tmp_path / "Juego"
    (root / "Data").mkdir(parents=True)
    (root / "Graphics" / "Titles").mkdir(parents=True)
    (root / "Audio").mkdir()
    (root / "Game.exe").write_bytes(b"MZ" + b"\0" * 98)
    (root / "Game.ini").write_bytes(b"[Game]\n")
    (root / "Data" / "Scripts.rxdata").write_bytes(b"x" * 10)
    (root / "Data" / "Map001.rxdata").write_bytes(b"x" * 20)
    (root / "Graphics" / "Titles" / "title.png").write_bytes(b"x" * 5)
    return root


def test_inventory(game_dir):
    scan = GameScanner().scan(game_dir)

    assert scan.root == game_dir.resolve()
    assert scan.files == ("Game.exe", "Game.ini")
    assert set(scan.directories) == {"Audio", "Data", "Graphics"}
    assert scan.relative_files == (
        "Data/Map001.rxdata",
        "Data/Scripts.rxdata",
        "Game.exe",
        "Game.ini",
        "Graphics/Titles/title.png",
    )
    assert scan.total_files == 5
    assert scan.total_size == 100 + 7 + 10 + 20 + 5
    assert scan.extension_counts[".rxdata"] == 2
    assert scan.truncated is False


def test_lookups_are_case_insensitive(game_dir):
    scan = GameScanner().scan(game_dir)

    assert scan.find_file("GAME.INI") == "Game.ini"
    assert scan.find_dir("data") == "Data"
    assert scan.find_relative("data\\SCRIPTS.rxdata") == "Data/Scripts.rxdata"
    assert scan.find_file("no_existe") is None
    assert scan.find_relative("Data/NoExiste.rxdata") is None


def test_files_with_suffix(game_dir):
    scan = GameScanner().scan(game_dir)

    assert scan.files_with_suffix(".EXE") == ("Game.exe",)
    assert scan.files_with_suffix(".rxdata", directory="data") == (
        "Data/Map001.rxdata",
        "Data/Scripts.rxdata",
    )
    # sin recursión: Graphics/Titles/title.png no está directamente en Graphics
    assert scan.files_with_suffix(".png", directory="Graphics") == ()
    assert scan.files_with_suffix(".rxdata", directory="NoExiste") == ()


def test_path_of(game_dir):
    scan = GameScanner().scan(game_dir)
    assert scan.path_of("Data/Scripts.rxdata").read_bytes() == b"x" * 10


def test_max_files_truncates(game_dir):
    scan = GameScanner(max_files=2).scan(game_dir)

    assert scan.truncated is True
    assert scan.total_files == 2


def test_symlinks_are_skipped(game_dir, tmp_path):
    outside = tmp_path / "fuera"
    outside.mkdir()
    (outside / "secreto.txt").write_text("no debe aparecer")
    try:
        os.symlink(outside, game_dir / "enlace", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("este sistema no permite crear enlaces simbólicos")

    scan = GameScanner().scan(game_dir)

    assert scan.skipped_symlinks == ("enlace",)
    assert not any("secreto" in f for f in scan.relative_files)


@pytest.mark.skipif(sys.platform != "win32", reason="las junctions solo existen en Windows")
def test_windows_junctions_are_skipped(game_dir, tmp_path):
    import _winapi

    outside = tmp_path / "fuera"
    outside.mkdir()
    (outside / "secreto.txt").write_text("no debe aparecer")
    _winapi.CreateJunction(str(outside), str(game_dir / "enlace"))

    scan = GameScanner().scan(game_dir)

    assert scan.skipped_symlinks == ("enlace",)
    assert not any("secreto" in f for f in scan.relative_files)


def test_unreadable_directory_is_reported(game_dir, monkeypatch):
    real_scandir = os.scandir

    def fake_scandir(path):
        if Path(path).name == "Graphics":
            raise PermissionError(13, "Permiso denegado")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)
    scan = GameScanner().scan(game_dir)

    assert scan.unreadable == ("Graphics/",)
    assert "Data/Scripts.rxdata" in scan.relative_files  # el resto sí se escanea


def test_unreadable_file_is_reported(game_dir, monkeypatch):
    real_scandir = os.scandir

    class BrokenEntry:
        """DirEntry cuyo stat() falla (fichero borrado o sin permisos)."""

        def __init__(self, entry):
            self._entry = entry
            self.name, self.path = entry.name, entry.path

        def __getattr__(self, attr):
            return getattr(self._entry, attr)

        def stat(self, **_kwargs):
            raise PermissionError(13, "Permiso denegado")

    def fake_scandir(path):
        entries = list(real_scandir(path))
        return [BrokenEntry(e) if e.name == "Game.ini" else e for e in entries]

    monkeypatch.setattr(os, "scandir", fake_scandir)
    scan = GameScanner().scan(game_dir)

    assert scan.unreadable == ("Game.ini",)
    assert "Game.ini" not in scan.relative_files


def test_nonexistent_path_raises(tmp_path):
    with pytest.raises(GameScanError, match="no existe"):
        GameScanner().scan(tmp_path / "no_existe")


def test_file_instead_of_folder_raises(game_dir):
    with pytest.raises(GameScanError, match="no es una carpeta"):
        GameScanner().scan(game_dir / "Game.exe")


def test_empty_folder(tmp_path):
    scan = GameScanner().scan(tmp_path)

    assert scan.files == ()
    assert scan.total_files == 0
