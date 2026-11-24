import pytest

from conftest import build_game_ini
from pokemon_to_linux.engines.base import DETECTION_THRESHOLD
from pokemon_to_linux.engines.detector import detect_engine
from pokemon_to_linux.engines.rpgmaker_xp.detector import RPGMakerXPDetector
from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScanner


def detect(path):
    return RPGMakerXPDetector().detect(GameScanner().scan(path))


def indicators(result):
    return {e.indicator for e in result.evidence}


# --- Juegos que sí son RPG Maker XP --------------------------------------


def test_classic_rgss_game(make_game):
    result = detect(make_game())

    assert result.detected is True
    assert result.engine == "rpgmaker_xp"
    assert result.confidence == pytest.approx(1.0)
    assert result.executable == "Game.exe"
    assert result.runtime == "rgss1"
    assert result.warnings == ()
    assert result.details["title"] == "Juego de prueba"
    assert result.details["architecture"] == "i386"
    assert result.details["bits"] == 32
    assert result.details["requires_opengl"] is False
    assert result.details["rgss_dlls"] == ["RGSS104E.dll"]
    assert result.details["rxdata_files"] == 2


def test_mkxp_z_game_like_pokemon_z(make_game):
    game = make_game(
        exe="mkxp-z",
        dlls=("RGSS102E.dll", "RGSS102J.dll", "RGSS104E.dll"),
        extra={"mkxp.json": b"{}", "preload.rb": b"# parche"},
    )
    result = detect(game)

    assert result.detected is True
    assert result.runtime == "mkxp-z"
    assert result.details["sdl2_version"] == "2.0.12"
    assert result.details["requires_opengl"] is True
    assert result.details["mkxp_config"] is True
    assert result.details["preload_script"] is True
    assert result.warnings == ()


def test_encrypted_game_with_rgssad(make_game):
    result = detect(make_game(data=(), extra={"Game.rgssad": b"RGSSAD\0\x01"}))

    assert result.detected is True
    assert "xp_data" in indicators(result)
    # Con el archivo cifrado, que falte Data/Scripts.rxdata es normal.
    assert not any("scripts" in w for w in result.warnings)


def test_lowercase_names_are_found(make_game):
    """En Linux importan las mayúsculas: data/ y game.ini también valen."""
    game = make_game(no_ini=True, data_dir="data", exe_name="game.exe")
    (game / "game.ini").write_bytes(build_game_ini())

    result = detect(game)

    assert result.detected is True
    assert result.executable == "game.exe"


def test_game_without_ini_is_still_detected_by_data(make_game):
    result = detect(make_game(no_ini=True))

    assert result.detected is True
    assert "game_ini" not in indicators(result)


# --- Juegos que NO deben detectarse ---------------------------------------


def test_only_game_exe_is_not_enough(make_game):
    """La guía lo exige: Game.exe por sí solo no identifica el motor."""
    result = detect(make_game(no_ini=True, dlls=(), data=(), resources=False))

    assert result.detected is False
    assert result.confidence < DETECTION_THRESHOLD
    assert result.executable == "Game.exe"


def test_empty_folder(tmp_path):
    result = detect(tmp_path)

    assert result.detected is False
    assert result.confidence == 0
    assert result.executable is None


def test_rpg_maker_vx_ace_is_rejected(make_game):
    game = make_game(
        ini=build_game_ini(library="System\\RGSS301.dll", scripts="Data\\Scripts.rvdata2"),
        dlls=("RGSS301.dll",),
        data=("Scripts.rvdata2", "Map001.rvdata2"),
    )
    result = detect(game)

    assert result.detected is False
    assert any("VX" in w for w in result.warnings)
    assert any(e.weight < 0 for e in result.evidence)


def test_resources_alone_are_not_conclusive(make_game):
    result = detect(make_game(no_ini=True, exe=None, dlls=(), data=()))

    assert result.detected is False


# --- Advertencias ----------------------------------------------------------


def test_missing_library_dll_warns_for_classic_runtime(make_game):
    result = detect(make_game(dlls=()))

    assert result.detected is True
    assert any("RGSS104E.dll" in w and "no está" in w for w in result.warnings)


def test_missing_library_dll_is_fine_with_mkxp_z(make_game):
    result = detect(make_game(exe="mkxp-z", dlls=()))

    assert result.runtime == "mkxp-z"
    assert not any("DLL" in w for w in result.warnings)


def test_rtp_warning(make_game):
    result = detect(make_game(ini=build_game_ini(rtp1="Standard")))

    assert result.details["rtp"] == ["Standard"]
    assert any("RTP" in w for w in result.warnings)


def test_missing_scripts_file_warns(make_game):
    result = detect(make_game(data=("Map001.rxdata",)))

    assert any("scripts" in w for w in result.warnings)


def test_multiple_executables_prefers_game_exe(make_game):
    result = detect(make_game(extra={"Editor.exe": b"MZ"}))

    assert result.executable == "Game.exe"
    assert result.details["other_executables"] == ["Editor.exe"]
    assert any("Editor.exe" in w for w in result.warnings)


def test_single_executable_with_other_name_is_chosen(make_game):
    result = detect(make_game(no_ini=True, exe_name="Pokemon.exe"))

    assert result.executable == "Pokemon.exe"


def test_ambiguous_executables_without_game_exe(make_game):
    result = detect(make_game(no_ini=True, exe=None, extra={"A.exe": b"MZ", "B.exe": b"MZ"}))

    assert result.executable is None
    assert any("varios ejecutables" in w for w in result.warnings)


def test_invalid_executable_warns(make_game):
    result = detect(make_game(exe="garbage"))

    assert result.detected is True  # el resto de indicios sigue siendo XP
    assert result.runtime == "rgss1"
    assert any("no es un ejecutable" in w for w in result.warnings)


def test_unreadable_ini_warns(make_game):
    result = detect(make_game(ini=b"esto no es un ini"))

    assert any("Game.ini" in w for w in result.warnings)


# --- Formato de salida y selección de motor --------------------------------


def test_to_dict_follows_guide_schema(make_game):
    data = detect(make_game()).to_dict()

    for key in ("detected", "engine", "confidence", "executable", "runtime", "warnings"):
        assert key in data
    assert data["engine"] == "rpgmaker_xp"
    assert isinstance(data["warnings"], list)
    assert isinstance(data["evidence"], list)


def test_detect_engine_returns_best_result(make_game):
    scan = GameScanner().scan(make_game())
    assert detect_engine(scan).engine == "rpgmaker_xp"
    assert detect_engine(scan).detected is True


def test_detect_engine_without_detectors(tmp_path):
    result = detect_engine(GameScanner().scan(tmp_path), detectors=[])

    assert result.engine == "unknown"
    assert result.detected is False
