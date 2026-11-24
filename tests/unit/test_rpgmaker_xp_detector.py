import pytest

from conftest import build_game_ini
from pokemon_to_linux.engines.base import DETECTION_THRESHOLD
from pokemon_to_linux.engines.detector import detect_engine
from pokemon_to_linux.engines.rpgmaker_xp.detector import RPGMakerXPDetector, parse_rgss_name
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


# --- DLL RGSS: versión y arquitectura --------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("RGSS104E.dll", {"version": "1.04", "edition": "inglesa"}),
        ("rgss102j.DLL", {"version": "1.02", "edition": "japonesa"}),
        ("RGSS100.dll", {"version": "1.00", "edition": "sin indicar"}),
        ("RGSS103X.dll", {"version": "1.03", "edition": "desconocida (x)"}),
        ("RGSS301.dll", {"version": "3.01", "edition": "sin indicar"}),
        ("otra.dll", None),
    ],
)
def test_parse_rgss_name(name, expected):
    assert parse_rgss_name(name) == expected


def test_rgss_dll_info(make_game):
    result = detect(make_game(dlls=("RGSS102J.dll", "RGSS104E.dll")))

    assert result.details["rgss_library_version"] == "1.04"
    info = {i["name"]: i for i in result.details["rgss_dll_info"]}
    assert info["RGSS104E.dll"] == {
        "name": "RGSS104E.dll",
        "path": "RGSS104E.dll",
        "version": "1.04",
        "edition": "inglesa",
        "architecture": "i386",
        "bits": 32,
        "valid": True,
        "error": None,
        "imports": [],
    }
    assert info["RGSS102J.dll"]["edition"] == "japonesa"


def test_library_in_subfolder_is_inspected(make_game, make_pe):
    game = make_game(
        ini=build_game_ini(library=r"System\RGSS104E.dll"),
        dlls=(),
        extra={"System/RGSS104E.dll": make_pe(dll=True)},
    )
    result = detect(game)

    assert [i["path"] for i in result.details["rgss_dll_info"]] == ["System/RGSS104E.dll"]
    assert result.warnings == ()


def test_corrupt_library_dll_warns(make_game):
    result = detect(make_game(dlls=(), extra={"RGSS104E.dll": b"basura"}))

    assert result.details["rgss_dll_info"][0]["valid"] is False
    assert any("RGSS104E.dll no es una DLL válida" in w for w in result.warnings)


def test_library_that_is_an_exe_warns(make_game, make_pe):
    result = detect(make_game(dlls=(), extra={"RGSS104E.dll": make_pe(dll=False)}))

    assert any("es un ejecutable, no una DLL" in w for w in result.warnings)


def test_library_architecture_mismatch_warns(make_game, make_pe):
    dll64 = make_pe(machine=0x8664, pe32_plus=True, dll=True)
    result = detect(make_game(dlls=(), extra={"RGSS104E.dll": dll64}))

    assert any(
        "x86_64" in w and "i386" in w and "no pueden funcionar juntos" in w for w in result.warnings
    )


def test_corrupt_library_dll_is_fine_with_mkxp_z(make_game):
    """mkxp-z no carga la DLL, así que una DLL rota no es un problema."""
    result = detect(make_game(exe="mkxp-z", dlls=(), extra={"RGSS104E.dll": b"basura"}))

    assert result.details["rgss_dll_info"][0]["valid"] is False
    assert result.warnings == ()


# --- Dependencias PE ---------------------------------------------------------


def test_dependencies_of_classic_game(make_game):
    deps = detect(make_game()).details["dependencies"]

    assert deps == {
        "system": ["kernel32.dll", "user32.dll", "gdi32.dll"],
        "bundled": [],
        "redistributable": [],
        "missing": [],
    }


def test_missing_dependency_warns(make_game, make_pe):
    exe = make_pe(imports=("kernel32.dll", "fmod.dll"))
    result = detect(make_game(exe=None, extra={"Game.exe": exe}))

    assert result.details["dependencies"]["missing"] == ["fmod.dll"]
    assert any("fmod.dll" in w and "no arrancará" in w for w in result.warnings)


def test_bundled_dependency_is_fine(make_game, make_pe):
    exe = make_pe(imports=("kernel32.dll", "fmod.dll"))
    result = detect(make_game(exe=None, extra={"Game.exe": exe, "fmod.dll": make_pe(dll=True)}))

    assert result.details["dependencies"]["bundled"] == ["fmod.dll"]
    assert result.warnings == ()


def test_redistributable_dependency_warns(make_game, make_pe):
    exe = make_pe(imports=("kernel32.dll", "MSVCP140.dll"))
    result = detect(make_game(exe=None, extra={"Game.exe": exe}))

    assert result.details["dependencies"]["redistributable"] == ["msvcp140.dll"]
    assert any("redistribuibles" in w for w in result.warnings)


def test_library_dependencies_are_checked_for_classic_runtime(make_game, make_pe):
    dll = make_pe(dll=True, imports=("kernel32.dll", "rara.dll"))
    result = detect(make_game(dlls=(), extra={"RGSS104E.dll": dll}))

    assert result.details["library_dependencies"]["missing"] == ["rara.dll"]
    assert any(w.startswith("RGSS104E.dll necesita") for w in result.warnings)


def test_library_dependencies_ignored_with_mkxp_z(make_game, make_pe):
    dll = make_pe(dll=True, imports=("rara.dll",))
    result = detect(make_game(exe="mkxp-z", dlls=(), extra={"RGSS104E.dll": dll}))

    assert "library_dependencies" not in result.details
    assert result.warnings == ()
