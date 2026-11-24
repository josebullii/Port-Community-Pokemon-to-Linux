import os

import pytest

from pokemon_to_linux.application.analyze_game import (
    GameScanError,
    analyze_game,
    engine_display_name,
)
from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScanner


def test_analyze_detected_game(make_game):
    analysis = analyze_game(make_game())

    assert analysis.detection.detected is True
    assert analysis.warnings == ()
    data = analysis.to_dict()
    assert data["game_path"] == str(analysis.path)
    assert data["engine"] == "rpgmaker_xp"
    assert data["scan"]["total_files"] == analysis.scan.total_files
    assert data["scan"]["truncated"] is False


def test_scan_warnings_come_first(make_game):
    game = make_game(dlls=())  # el detector avisa de la DLL que falta
    analysis = analyze_game(game, scanner=GameScanner(max_files=2))

    assert "análisis es parcial" in analysis.warnings[0]
    assert analysis.to_dict()["scan"]["truncated"] is True


def test_symlink_warning(make_game, tmp_path):
    game = make_game()
    try:
        os.symlink(tmp_path, game / "enlace", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("este sistema no permite crear enlaces simbólicos")

    analysis = analyze_game(game)

    assert any("enlaces simbólicos" in w for w in analysis.warnings)


def test_invalid_path_raises(tmp_path):
    with pytest.raises(GameScanError):
        analyze_game(tmp_path / "no_existe")


def test_engine_display_name():
    assert engine_display_name("rpgmaker_xp") == "RPG Maker XP"
    assert engine_display_name("otro") == "Desconocido"


def test_unreadable_warning(make_game, monkeypatch):
    from pathlib import Path

    real_scandir = os.scandir

    def fake_scandir(path):
        if Path(path).name == "Audio":
            raise PermissionError(13, "Permiso denegado")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)
    analysis = analyze_game(make_game())

    assert any("No se han podido leer" in w and "Audio/" in w for w in analysis.warnings)
