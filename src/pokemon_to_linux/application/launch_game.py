"""Casos de uso: preparar, lanzar y detener un juego con Wine.

Flujo de la guía: analizar → verificar → preparar prefijo → probar → lanzar.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pokemon_to_linux.application.analyze_game import GameAnalysis, analyze_game
from pokemon_to_linux.application.profiles import match_profile, resolve_folder
from pokemon_to_linux.domain.profile import GameProfile
from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.wine.prefix_manager import (
    Prefix,
    PrefixManager,
    TestProgramResult,
    resolve_arch,
    slugify,
    validate_game_id,
)
from pokemon_to_linux.infrastructure.wine.process_manager import (
    GameProcess,
    LaunchSpec,
    ProcessManager,
)
from pokemon_to_linux.infrastructure.wine.wine_manager import (
    WineInstallation,
    wine_environment,
)

log = get_logger(__name__)

MISSING_32_BIT_HINT = (
    "Wine no puede ejecutar programas de 32 bits en este sistema. "
    "En Debian/Ubuntu: sudo dpkg --add-architecture i386 && sudo apt update && "
    "sudo apt install wine32:i386. En otras distribuciones, instala el soporte "
    "de 32 bits (multilib) de Wine."
)

GAME_WINEDEBUG = "fixme-all"
"""Al jugar se conservan los mensajes ``err`` de Wine: sirven para el diagnóstico."""


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    game_id: str
    analysis: GameAnalysis
    executable: Path
    prefix: Prefix
    spec: LaunchSpec
    prefix_created: bool
    test_result: TestProgramResult | None
    """Resultado del programa de prueba si el prefijo se acaba de crear."""
    profile: GameProfile | None = None
    save_dirs: tuple[Path, ...] = ()
    """Carpetas de partidas (rutas reales). Con Wine suelen estar dentro del prefijo."""
    config_dirs: tuple[Path, ...] = ()


def prepare_launch(
    game_path: Path | str,
    *,
    wine: WineInstallation,
    prefixes: PrefixManager,
    game_id: str | None = None,
    arch: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    profiles: Sequence[GameProfile] = (),
) -> LaunchPlan:
    """Analiza el juego, prepara su prefijo y devuelve todo lo necesario para lanzarlo.

    Si algún perfil de ``profiles`` corresponde al juego, se aplica: su
    arquitectura (salvo que se pida otra con ``arch``) y su entorno (que
    ``extra_env`` puede sobrescribir).

    Puede tardar (crear un prefijo lleva segundos): en la interfaz gráfica
    debe llamarse fuera del hilo principal.
    """
    analysis = analyze_game(game_path)
    detection = analysis.detection
    if not detection.detected:
        raise LaunchError(
            "No se reconoce el motor del juego; por ahora solo se admite RPG Maker XP."
        )
    if detection.executable is None:
        raise LaunchError("No se ha podido identificar el ejecutable del juego.")

    profile = match_profile(analysis, profiles)
    bits = detection.details.get("bits")
    if game_id is None:
        game_id = slugify(detection.details.get("title") or analysis.path.name)
    validate_game_id(game_id)
    arch = resolve_arch(bits, arch or (profile.arch if profile else None))

    created = prefixes.get(game_id) is None
    prefix = prefixes.ensure(game_id, arch)

    test_result = None
    if created and bits in (32, 64):
        test_result = prefixes.run_test_program(prefix, bits)
        if not test_result.ok:
            # Si se quedara, el siguiente intento lo reutilizaría sin comprobarlo
            # y el juego fallaría con un error críptico de Wine.
            prefixes.delete(game_id)
            hint = MISSING_32_BIT_HINT if bits == 32 else "Revisa la instalación de Wine."
            raise LaunchError(
                f"El prefijo {game_id} no puede ejecutar programas de {bits} bits. {hint}"
            )

    executable = analysis.scan.path_of(detection.executable)
    env = wine_environment(
        prefix.path,
        debug=GAME_WINEDEBUG,
        extra={**(profile.environment if profile else {}), **(extra_env or {})},
    )
    stop = (str(wine.wineserver), "-k") if wine.wineserver else None
    spec = LaunchSpec(
        game_id=game_id,
        program=wine.wine,
        arguments=(str(executable),),
        working_dir=analysis.path,
        environment=env,
        stop_command=stop,
    )

    def folders(paths: tuple[str, ...]) -> tuple[Path, ...]:
        return tuple(
            resolve_folder(p, prefix_path=prefix.path, game_dir=analysis.path) for p in paths
        )

    log.info(
        "Lanzamiento preparado: %s (%s, prefijo %s, perfil %s)",
        game_id,
        executable.name,
        prefix.arch,
        profile.id if profile else "ninguno",
    )
    return LaunchPlan(
        game_id,
        analysis,
        executable,
        prefix,
        spec,
        created,
        test_result,
        profile=profile,
        save_dirs=folders(profile.save_dirs) if profile else (),
        config_dirs=folders(profile.config_dirs) if profile else (),
    )


def launch_game(plan: LaunchPlan, processes: ProcessManager) -> GameProcess:
    return processes.launch(plan.spec)


def stop_game(game_id: str, processes: ProcessManager) -> None:
    processes.stop(game_id)
