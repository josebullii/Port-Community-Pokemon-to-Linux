import json

import pytest

from pokemon_to_linux import __version__
from pokemon_to_linux.cli import EXIT_DETECTED, EXIT_ERROR, EXIT_NOT_DETECTED, main
from pokemon_to_linux.infrastructure.logging.logger import LOG_FILE_NAME, ROOT_LOGGER_NAME


@pytest.fixture(autouse=True)
def _isolated_logs(xdg_tmp):
    """La CLI escribe el log de la app: que vaya a un directorio temporal."""
    return xdg_tmp


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


def test_analysis_is_written_to_app_log(make_game, xdg_tmp):
    import logging

    main(["analyze", str(make_game())])
    for handler in logging.getLogger(ROOT_LOGGER_NAME).handlers:
        handler.flush()

    log = (xdg_tmp / "state" / "pokemon-to-linux" / "logs" / LOG_FILE_NAME).read_text("utf-8")
    assert "Análisis de" in log
    assert "motor=rpgmaker_xp detectado=True" in log


def test_cli_works_when_log_cannot_be_written(make_game, capsys, monkeypatch):
    def broken(*_args, **_kwargs):
        raise PermissionError(13, "Permiso denegado")

    monkeypatch.setattr("pokemon_to_linux.cli.setup_logging", broken)

    assert main(["analyze", str(make_game())]) == EXIT_DETECTED
    assert "no se puede escribir el log" in capsys.readouterr().err


def test_rgss_line_matches_library_in_subfolder(make_game, make_pe, capsys):
    from conftest import build_game_ini

    game = make_game(
        ini=build_game_ini(library=r"System\RGSS104E.dll"),
        dlls=(),
        extra={"System/RGSS104E.dll": make_pe(dll=True)},
    )
    main(["analyze", str(game)])

    assert r"RGSS:        System\RGSS104E.dll (versión 1.04, i386)" in capsys.readouterr().out
