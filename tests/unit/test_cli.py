import json

import pytest

from pokemon_to_linux import __version__
from pokemon_to_linux.cli import EXIT_DETECTED, EXIT_ERROR, EXIT_NOT_DETECTED, main


def test_analyze_text_report(make_game, capsys):
    code = main(["analyze", str(make_game(exe="mkxp-z"))])
    out = capsys.readouterr().out

    assert code == EXIT_DETECTED
    assert "RPG Maker XP (detectado, confianza 100%)" in out
    assert "mkxp-z (SDL2 2.0.12)" in out
    assert "RGSS:        RGSS104E.dll (versión 1.04, i386)" in out
    assert "Game.exe (i386, 32 bits, gui)" in out
    assert "OpenGL:      sí" in out
    assert "DLL:         2 de sistema, 0 incluidas, 0 redistribuibles, 0 faltan" in out
    assert "(ninguna)" in out


def test_analyze_json(make_game, capsys):
    code = main(["analyze", str(make_game()), "--json"])
    data = json.loads(capsys.readouterr().out)

    assert code == EXIT_DETECTED
    assert data["detected"] is True
    assert data["engine"] == "rpgmaker_xp"
    assert data["runtime"] == "rgss1"


def test_not_detected_exit_code(tmp_path, capsys):
    code = main(["analyze", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == EXIT_NOT_DETECTED
    assert "no detectado" in out
    assert "Ejecutable:  no identificado" in out


def test_invalid_path_exit_code(tmp_path, capsys):
    code = main(["analyze", str(tmp_path / "no_existe")])

    assert code == EXIT_ERROR
    assert "no existe" in capsys.readouterr().err


def test_warnings_are_listed(make_game, capsys):
    main(["analyze", str(make_game(dlls=()))])

    assert "- Game.ini indica RGSS104E.dll" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("size", "expected"),
    [(512, "512 B"), (1536, "1,5 KB"), (915_931_136, "873,5 MB"), (3 * 1024**3, "3,0 GB")],
)
def test_format_size_uses_spanish_decimals(size, expected):
    from pokemon_to_linux.cli import _format_size

    assert _format_size(size) == expected


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_command_is_required(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])

    assert exc.value.code == 2
