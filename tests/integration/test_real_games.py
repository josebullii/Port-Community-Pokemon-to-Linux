"""Pruebas con juegos reales (opcionales).

Los juegos no se incluyen en el repositorio. Para ejecutarlas, indica la
ruta de tu copia legítima:

    PTL_POKEMON_Z_PATH="/ruta/a/POKEMON Z V2.19" pytest -m realgame

La que lanza el juego necesita además Wine y una sesión gráfica (vale
``xvfb-run``). Usa un prefijo temporal: nunca toca el del usuario, donde
están sus partidas.
"""

import os
import time

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
    assert details["rgss_library_version"] == "1.04"
    assert all(i["valid"] and i["architecture"] == "i386" for i in details["rgss_dll_info"])
    assert "opengl32.dll" in details["dependencies"]["system"]
    assert details["dependencies"]["missing"] == []
    assert details["dependencies"]["redistributable"] == []
    assert analysis.warnings == ()


@pytest.mark.wine
def test_pokemon_z_starts_with_wine(qapp, tmp_path):
    """Pokémon Z arranca con su perfil, inicializa OpenGL y sigue en marcha."""
    from pokemon_to_linux.application.check_requirements import check_requirements
    from pokemon_to_linux.application.diagnose_output import OutputDiagnoser
    from pokemon_to_linux.application.launch_game import launch_game, prepare_launch, stop_game
    from pokemon_to_linux.infrastructure.filesystem.profile_store import load_profiles
    from pokemon_to_linux.infrastructure.wine.prefix_manager import PrefixManager
    from pokemon_to_linux.infrastructure.wine.process_manager import ProcessManager, ProcessState
    from pokemon_to_linux.infrastructure.wine.wine_manager import WineManager

    wine = WineManager().detect()
    if wine is None:
        pytest.skip("Wine no está instalado")
    if not os.environ.get("DISPLAY"):
        pytest.skip("hace falta una sesión gráfica (p. ej. xvfb-run)")

    analysis = analyze_game(POKEMON_Z)
    blocking = [c for c in check_requirements(analysis) if c.blocking]
    assert blocking == [], blocking

    plan = prepare_launch(
        POKEMON_Z,
        wine=wine,
        prefixes=PrefixManager(tmp_path / "prefixes", wine),
        profiles=load_profiles(None).profiles,
        analysis=analysis,
    )
    assert plan.profile is not None and plan.profile.id == "pokemon-z"
    assert plan.save_dirs[0].parts[-2:] == ("Saved Games", "Pokemon Z")

    processes = ProcessManager(log_dir=tmp_path / "logs")
    process = launch_game(plan, processes)
    lines: list[str] = []
    diagnoser = OutputDiagnoser(plan.profile)
    process.output.connect(lines.append)
    process.output.connect(diagnoser.feed)

    # mkxp-z escribe "GL Version" cuando ha creado la ventana OpenGL.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not any("GL Version" in x for x in lines):
        if process.wait(500):
            break
    started = any("GL Version" in x for x in lines)
    if started:
        process.wait(10_000)  # unos segundos más: no debe cerrarse solo
        still_running = process.state is ProcessState.RUNNING
    stop_game(plan.game_id, processes)
    assert process.wait(60_000)

    output = "\n".join(lines)
    assert started, output
    assert still_running, output
    assert process.outcome.state is ProcessState.STOPPED
    assert diagnoser.problems == (), output
