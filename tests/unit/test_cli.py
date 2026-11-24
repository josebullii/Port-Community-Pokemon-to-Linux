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


# --- wine y run (con Wine simulado) --------------------------------------------


@pytest.fixture
def no_wine(monkeypatch):
    monkeypatch.setattr("pokemon_to_linux.cli.WineManager.detect", lambda self: None)


@pytest.fixture
def fake_wine(monkeypatch, tmp_path):
    """Wine simulado: detect() devuelve una instalación y PrefixManager usa FakeWine."""
    from test_prefix_manager import FakeWine

    from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixManager
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineInstallation

    state = {"fake": FakeWine()}
    wine = WineInstallation(
        tmp_path / "no-existe" / "wine", tmp_path / "no-existe" / "wineserver",
        "9.0", None, "wine-9.0",
    )  # fmt: skip
    monkeypatch.setattr("pokemon_to_linux.cli.WineManager.detect", lambda self: wine)
    monkeypatch.setattr(
        "pokemon_to_linux.cli.PrefixManager",
        lambda d, w: PrefixManager(d, w, runner=state["fake"], registry_wait=0.2),
    )
    return state


def test_wine_not_installed(no_wine, capsys):
    assert main(["wine"]) == EXIT_NOT_DETECTED
    assert "Wine no está instalado" in capsys.readouterr().err


def test_run_without_wine(no_wine, make_game, capsys):
    assert main(["run", str(make_game(exe="runnable"))]) == EXIT_ERROR
    assert "no lo instala por ti" in capsys.readouterr().err


def test_wine_info(fake_wine, capsys):
    assert main(["wine"]) == 0
    out = capsys.readouterr().out
    assert "wine-9.0" in out
    assert "wineserver:" in out


def test_wine_probe_ok(fake_wine, capsys):
    assert main(["wine", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "64 bits:     sí" in out
    assert "32 bits:     sí" in out


def test_wine_probe_without_32_bit_support(fake_wine, capsys):
    from test_prefix_manager import FakeWine

    fake_wine["fake"] = FakeWine(program_code=1)
    assert main(["wine", "--probe"]) == EXIT_NOT_DETECTED
    out = capsys.readouterr().out
    assert "32 bits:     NO" in out
    assert "wine32:i386" in out


def test_run_unknown_game(fake_wine, tmp_path, capsys):
    assert main(["run", str(tmp_path)]) == EXIT_ERROR
    assert "motor" in capsys.readouterr().err


def test_run_when_wine_fails_to_start(qapp, fake_wine, make_game, capsys):
    code = main(["run", str(make_game(exe="runnable")), "--id", "prueba"])
    out = capsys.readouterr().out

    assert code == EXIT_NOT_DETECTED
    assert "Juego:       prueba" in out
    assert "(win64)" in out
    assert "Fin: failed" in out
    assert "Log:" in out
