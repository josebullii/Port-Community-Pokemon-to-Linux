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


def fake_host(env=None, libraries=None):
    from pokemon_to_linux.infrastructure.system.host import HostSystem

    host = HostSystem(env={"DISPLAY": ":0"} if env is None else env)
    host.__dict__["shared_libraries"] = {"libGL.so.1": {32, 64}} if libraries is None else libraries
    return host


@pytest.fixture(autouse=True)
def host(monkeypatch):
    """Sistema simulado con pantalla y OpenGL: las pruebas no dependen del equipo."""
    state = {"host": fake_host()}
    monkeypatch.setattr("pokemon_to_linux.cli.HostSystem", lambda: state["host"])
    return state


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


def test_run_ctrl_c_while_preparing(fake_wine, make_game, monkeypatch, capsys):
    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("pokemon_to_linux.cli.prepare_launch", interrupted)

    assert main(["run", str(make_game(exe="runnable"))]) == 130
    err = capsys.readouterr().err
    assert "Cancelado." in err
    assert "Traceback" not in err


def test_wine_probe_ctrl_c(fake_wine, monkeypatch, capsys):
    from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixManager

    def interrupted(self, prefix, bits, timeout=120):
        raise KeyboardInterrupt

    monkeypatch.setattr(PrefixManager, "run_test_program", interrupted)

    assert main(["wine", "--probe"]) == 130
    assert "Cancelado." in capsys.readouterr().err


def test_wine_probe_prefix_creation_fails(fake_wine, capsys):
    from test_prefix_manager import FakeWine

    fake_wine["fake"] = FakeWine(wineboot_code=1)

    assert main(["wine", "--probe"]) == EXIT_ERROR
    assert "no se pudo crear un prefijo" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["wine"], ["run", "."]])
def test_broken_wine_is_an_error(command, monkeypatch, capsys):
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineError

    def broken(self):
        raise WineError("wine --version falló (código 1)")

    monkeypatch.setattr("pokemon_to_linux.cli.WineManager.detect", broken)

    assert main(command) == EXIT_ERROR
    assert "wine --version falló" in capsys.readouterr().err


# --- Requisitos, perfiles y diagnóstico (sprint 4) ---------------------------------

PROFILE = """\
schema = 1
id = "prueba"
name = "Juego de prueba"
[match]
titles = ["Juego de prueba"]
[saves]
paths = ["%USERPROFILE%/Saved Games/Prueba"]
[compatibility]
status = "partial"
notes = "Solo para pruebas"
[[known_issues]]
id = "lento"
symptom = "Va lento"
solution = "Quita VSync"
"""


@pytest.fixture
def user_profile(xdg_tmp):
    folder = xdg_tmp / "config" / "pokemon-to-linux" / "profiles"
    folder.mkdir(parents=True)
    (folder / "prueba.toml").write_text(PROFILE, encoding="utf-8")
    return folder


def test_run_refuses_when_a_requirement_is_missing(fake_wine, host, make_game, capsys):
    host["host"] = fake_host(env={})

    code = main(["run", str(make_game(exe="runnable"))])
    captured = capsys.readouterr()

    assert code == EXIT_ERROR
    assert "[ERROR]  Sesión gráfica" in captured.out
    assert "--ignore-checks" in captured.err
    assert "Preparando" not in captured.out


def test_run_ignore_checks(qapp, fake_wine, host, make_game, capsys):
    host["host"] = fake_host(env={})

    code = main(["run", str(make_game(exe="runnable")), "--ignore-checks"])
    out = capsys.readouterr().out

    assert code == EXIT_NOT_DETECTED  # Wine simulado: el proceso no arranca
    assert "Se lanza igualmente" in out
    assert "Preparando" in out


def test_run_missing_32_bit_opengl(fake_wine, host, make_game, capsys):
    host["host"] = fake_host(libraries={"libGL.so.1": {64}})

    assert main(["run", str(make_game(exe="mkxp-z"))]) == EXIT_ERROR
    out = capsys.readouterr().out
    assert "[ERROR]  OpenGL de 32 bits" in out
    assert "libgl1:i386" in out


def test_run_shows_profile_and_saves(qapp, fake_wine, user_profile, make_game, capsys):
    main(["run", str(make_game(exe="runnable"))])
    out = capsys.readouterr().out

    assert "Perfil:      Juego de prueba · Parcial" in out
    assert "Partidas:" in out
    assert "Saved Games" in out


def test_run_diagnoses_output(qapp, fake_wine, make_game, monkeypatch, tmp_path, capsys):
    import sys
    from pathlib import Path

    from pokemon_to_linux.infrastructure.wine.process_manager import LaunchSpec

    message = "Error creating window: No matching GL pixel format available"

    def fake_launch(plan, processes):
        spec = LaunchSpec(
            plan.game_id, Path(sys.executable), ("-c", f"print({message!r})"), tmp_path
        )
        return processes.launch(spec)

    monkeypatch.setattr("pokemon_to_linux.cli.launch_game", fake_launch)

    assert main(["run", str(make_game(exe="runnable"))]) == 0
    out = capsys.readouterr().out
    assert "Problemas detectados:" in out
    assert "no puede crear su ventana OpenGL" in out
    assert f"Salida: {message}" in out


def test_broken_user_profile_is_a_warning(qapp, fake_wine, user_profile, make_game, capsys):
    (user_profile / "roto.toml").write_text("schema = 1\n", encoding="utf-8")

    main(["run", str(make_game(exe="runnable"))])

    assert "Aviso: perfil ignorado" in capsys.readouterr().err


def test_check_ready(fake_wine, user_profile, make_game, capsys):
    code = main(["check", str(make_game(exe="mkxp-z"))])
    out = capsys.readouterr().out

    assert code == 0
    assert "Juego:       Juego de prueba (RPG Maker XP, mkxp-z, 32 bits)" in out
    assert "Perfil:      Juego de prueba · Parcial" in out
    assert "Solo para pruebas" in out
    assert "Wine:        wine-9.0" in out
    assert "[ok]     OpenGL de 32 bits: libGL.so.1" in out
    assert "%USERPROFILE%/Saved Games/Prueba" in out
    assert "- Va lento" in out
    assert "[ok]     Wine de 32 bits: Ejecuta programas de 32 bits (prefijo temporal)" in out
    assert "Listo para jugar: sí" in out


def test_check_without_32_bit_wine_is_not_ready(fake_wine, xdg_tmp, make_game, capsys):
    """Con wine64 sin wine32:i386, Wine existe pero no ejecuta Pokémon Z."""
    from test_prefix_manager import FakeWine

    fake_wine["fake"] = FakeWine(program_code=1)

    code = main(["check", str(make_game(exe="mkxp-z"))])
    out = capsys.readouterr().out

    assert code == EXIT_NOT_DETECTED
    assert "[ERROR]  Wine de 32 bits: No ejecuta programas de 32 bits" in out
    assert "wine32:i386" in out
    assert "Listo para jugar: no" in out
    # El prefijo temporal se borra aunque la prueba falle.
    probe = xdg_tmp / "cache" / "pokemon-to-linux" / "probe"
    assert not probe.exists() or not any(probe.iterdir())


def test_check_reuses_the_game_prefix(fake_wine, xdg_tmp, make_game, capsys):
    from pokemon_to_linux import cli

    wine = cli.WineManager().detect()
    prefixes = cli.PrefixManager(xdg_tmp / "data" / "pokemon-to-linux" / "prefixes", wine)
    prefixes.create("juego-de-prueba", "win64")
    fake_wine["fake"].calls.clear()

    assert main(["check", str(make_game(exe="mkxp-z"))]) == 0

    assert "(prefijo juego-de-prueba)" in capsys.readouterr().out
    assert ["wineboot", "--init"] not in fake_wine["fake"].commands()


def test_check_not_ready(no_wine, host, make_game, capsys):
    host["host"] = fake_host(libraries={})

    code = main(["check", str(make_game(exe="mkxp-z"))])
    out = capsys.readouterr().out

    assert code == EXIT_NOT_DETECTED
    assert "Perfil:      ninguno" in out
    assert "Wine:        no instalado" in out
    assert "no lo instala por ti" in out
    assert "[ERROR]  OpenGL de 32 bits" in out
    assert "Listo para jugar: no" in out


def test_check_unknown_game_and_bad_path(fake_wine, tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == EXIT_NOT_DETECTED
    assert "no reconocido" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "no")]) == EXIT_ERROR


def test_check_json(fake_wine, user_profile, make_game, capsys):
    assert main(["check", str(make_game(exe="mkxp-z")), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["ready"] is True
    assert data["profile"]["id"] == "prueba"
    assert data["profile"]["status"] == "partial"
    assert data["profile"]["known_issues"][0]["id"] == "lento"
    assert [c["id"] for c in data["checks"]] == ["display", "opengl", "filesystem", "wine"]
    assert data["wine"] == "wine-9.0"


def test_check_with_broken_wine(monkeypatch, make_game, capsys):
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineError

    def broken(self):
        raise WineError("wine --version falló (código 1)")

    monkeypatch.setattr("pokemon_to_linux.cli.WineManager.detect", broken)

    assert main(["check", str(make_game(exe="mkxp-z"))]) == EXIT_NOT_DETECTED
    assert "Wine:        wine --version falló" in capsys.readouterr().out


def test_profiles_command(user_profile, capsys):
    assert main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "pokemon-z" in out
    assert "Pokémon Z · Parcial" in out
    assert "prueba" in out
    assert str(user_profile) in out

    (user_profile / "roto.toml").write_text("id = 1\n", encoding="utf-8")
    assert main(["profiles"]) == EXIT_NOT_DETECTED
    assert "Ignorados por errores" in capsys.readouterr().out
