"""Pruebas con juegos reales (opcionales).

Los juegos no se incluyen en el repositorio. Para ejecutarlas, indica la
ruta de tu copia legítima:

    PTL_POKEMON_Z_PATH="/ruta/a/POKEMON Z V2.19" pytest -m realgame
"""

import os

import pytest

from pokemon_to_linux.application.analyze_game import analyze_game

POKEMON_Z = os.environ.get("PTL_POKEMON_Z_PATH")

pytestmark = [
    pytest.mark.realgame,
    pytest.mark.skipif(not POKEMON_Z, reason="define PTL_POKEMON_Z_PATH para probar Pokémon Z"),
]


def test_pokemon_z_v2_19_diagnosis():
    analysis = analyze_game(POKEMON_Z)
    result = analysis.detection
    details = result.details

    assert result.detected is True
    assert result.engine == "rpgmaker_xp"
    assert result.confidence >= 0.95
    assert result.executable == "Game.exe"
    assert result.runtime == "mkxp-z"
    assert details["title"] == "Pokemon Z"
    assert details["ini_library"] == "RGSS104E.dll"
    assert details["architecture"] == "i386"
    assert details["bits"] == 32
    assert details["requires_opengl"] is True
    assert details["sdl2_version"] == "2.0.12"
    assert details["mkxp_config"] is True
    assert details["preload_script"] is True
    assert details["rxdata_files"] > 500
    assert analysis.warnings == ()
