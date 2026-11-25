"""Interfaz de línea de comandos.

    pokemon-to-linux-cli analyze <carpeta> [--json]
    pokemon-to-linux-cli check <carpeta> [--id ID] [--json]
    pokemon-to-linux-cli wine [--probe]
    pokemon-to-linux-cli run <carpeta> [--id ID] [--arch win32|win64] [--timeout SEG]
                             [--ignore-checks]
    pokemon-to-linux-cli profiles

Códigos de salida:
- analyze: 0 = motor detectado, 1 = no detectado, 2 = error de uso o ruta.
- check: 0 = listo para jugar, 1 = falta algo, 2 = error de uso o ruta.
- wine: 0 = Wine disponible (y, con --probe, ejecuta 32 y 64 bits), 1 = no.
- run: el código de salida del juego; 1 si no terminó normalmente; 2 si no se pudo lanzar.
- profiles: 0 = todos los perfiles son válidos, 1 = alguno se ha ignorado.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import PureWindowsPath
from typing import TextIO

from PySide6.QtCore import QCoreApplication, QTimer

from pokemon_to_linux import APP_NAME, __version__
from pokemon_to_linux.application.analyze_game import (
    GameAnalysis,
    GameScanError,
    analyze_game,
    engine_display_name,
)
from pokemon_to_linux.application.check_requirements import check_requirements, check_wine_bits
from pokemon_to_linux.application.diagnose_output import Finding, OutputDiagnoser
from pokemon_to_linux.application.launch_game import (
    MISSING_32_BIT_HINT,
    NO_WINE_MESSAGE,
    LaunchError,
    LaunchPlan,
    default_game_id,
    launch_game,
    prepare_launch,
)
from pokemon_to_linux.application.profiles import match_profile
from pokemon_to_linux.config import AppPaths
from pokemon_to_linux.domain.profile import GameProfile
from pokemon_to_linux.domain.requirements import CheckStatus, RequirementCheck
from pokemon_to_linux.infrastructure.filesystem.profile_store import ProfileSet, load_profiles
from pokemon_to_linux.infrastructure.logging.logger import get_logger, setup_logging
from pokemon_to_linux.infrastructure.system.host import HostSystem
from pokemon_to_linux.infrastructure.wine.prefix_manager import ARCHES, PrefixError, PrefixManager
from pokemon_to_linux.infrastructure.wine.process_manager import (
    ProcessError,
    ProcessManager,
    ProcessState,
)
from pokemon_to_linux.infrastructure.wine.wine_manager import (
    WineError,
    WineInstallation,
    WineManager,
)

log = get_logger(__name__)

EXIT_OK = EXIT_DETECTED = 0
EXIT_NOT_DETECTED = 1
EXIT_ERROR = 2
EXIT_CANCELLED = 130  # convención de las shells para Ctrl+C


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            text = f"{value:.0f}" if unit == "B" else f"{value:.1f}".replace(".", ",")
            return f"{text} {unit}"
        value /= 1024
    raise AssertionError  # pragma: no cover


STATUS_MARKS = {
    CheckStatus.OK: "[ok]",
    CheckStatus.WARNING: "[aviso]",
    CheckStatus.ERROR: "[ERROR]",
    CheckStatus.UNKNOWN: "[?]",
}


def format_checks(checks: Sequence[RequirementCheck], *, only_problems: bool = False) -> list[str]:
    lines = []
    for check in checks:
        if only_problems and check.status is CheckStatus.OK:
            continue
        lines.append(f"    {STATUS_MARKS[check.status]:<8} {check.label}: {check.detail}")
        if check.hint and check.status is not CheckStatus.OK:
            lines.append(f"             → {check.hint}")
    return lines


def format_findings(findings: Sequence[Finding]) -> list[str]:
    lines = []
    for finding in findings:
        lines.append(f"  - {finding.issue.symptom}")
        lines.append(f"    Salida: {finding.line}")
        lines.append(f"    → {finding.issue.solution}")
    return lines


def _profile_summary(profile: GameProfile) -> str:
    return f"{profile.name} · {profile.status.label}"


def _format_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_report(analysis: GameAnalysis) -> str:
    d = analysis.detection
    det = d.details
    lines = [f"{APP_NAME} · diagnóstico", ""]

    def row(label: str, value: object) -> None:
        lines.append(f"  {label:<12} {value}")

    row("Carpeta:", analysis.path)
    if det.get("title"):
        row("Título:", det["title"])
    state = "detectado" if d.detected else "no detectado"
    row("Motor:", f"{engine_display_name(d.engine)} ({state}, confianza {d.confidence:.0%})")
    runtime = d.runtime
    if det.get("sdl2_version"):
        runtime += f" (SDL2 {det['sdl2_version']})"
    row("Runtime:", runtime)
    if det.get("rgss_library_version"):
        lib = det["ini_library"]
        lib_name = PureWindowsPath(lib).name.lower()
        info = next((i for i in det.get("rgss_dll_info", []) if i["name"].lower() == lib_name), {})
        extra = f", {info['architecture']}" if info.get("architecture") else ""
        row("RGSS:", f"{lib} (versión {det['rgss_library_version']}{extra})")
    if d.executable:
        exe = d.executable
        if "architecture" in det:
            exe += f" ({det['architecture']}, {det['bits']} bits, {det['subsystem']})"
        row("Ejecutable:", exe)
    else:
        row("Ejecutable:", "no identificado")
    if "requires_opengl" in det:
        row("OpenGL:", "sí" if det["requires_opengl"] else "no")
    if deps := det.get("dependencies"):
        row(
            "DLL:",
            f"{len(deps['system'])} de sistema, {len(deps['bundled'])} incluidas, "
            f"{len(deps['redistributable'])} redistribuibles, {len(deps['missing'])} faltan",
        )
    row(
        "Ficheros:",
        f"{_format_int(analysis.scan.total_files)} ({_format_size(analysis.scan.total_size)})",
    )

    lines += ["", "  Indicios:"]
    if d.evidence:
        lines += [f"    {e.weight:+.2f}  {e.detail}" for e in d.evidence]
    else:
        lines.append("    (ninguno)")

    lines += ["", "  Advertencias:"]
    if analysis.warnings:
        lines += [f"    - {w}" for w in analysis.warnings]
    else:
        lines.append("    (ninguna)")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pokemon-to-linux-cli",
        description=f"{APP_NAME}: herramientas de línea de comandos.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="comando")

    analyze = sub.add_parser("analyze", help="analiza la carpeta de un juego")
    analyze.add_argument("path", help="carpeta del juego")
    analyze.add_argument("--json", action="store_true", help="salida en JSON")

    check = sub.add_parser(
        "check", help="comprueba si el sistema tiene lo necesario para jugar a un juego"
    )
    check.add_argument("path", help="carpeta del juego")
    check.add_argument(
        "--id", dest="game_id", help="identificador del juego (por defecto, el título)"
    )
    check.add_argument("--json", action="store_true", help="salida en JSON")

    wine = sub.add_parser("wine", help="muestra la instalación de Wine")
    wine.add_argument(
        "--probe",
        action="store_true",
        help="comprueba si Wine ejecuta programas de 32 y 64 bits (crea un prefijo temporal)",
    )

    run = sub.add_parser("run", help="prepara el prefijo y lanza un juego con Wine")
    run.add_argument("path", help="carpeta del juego")
    run.add_argument(
        "--id", dest="game_id", help="identificador del juego (por defecto, el título)"
    )
    run.add_argument("--arch", choices=ARCHES, help="arquitectura del prefijo (por defecto win64)")
    run.add_argument(
        "--timeout", type=float, metavar="SEG", help="detiene el juego tras SEG segundos"
    )
    run.add_argument(
        "--ignore-checks",
        action="store_true",
        help="lanza el juego aunque falte un requisito del sistema",
    )

    sub.add_parser("profiles", help="lista los perfiles de compatibilidad")
    return parser


def _ensure_utf8(stream: TextIO) -> None:
    # En una tubería (p. ej. > fichero.json) Windows usaría cp1252: forzamos UTF-8.
    if hasattr(stream, "reconfigure") and not stream.isatty():
        stream.reconfigure(encoding="utf-8", errors="replace")


def _setup_file_logging() -> None:
    """Mismo fichero de log que la interfaz gráfica, sin ensuciar la consola.

    Si no se puede crear (permisos, disco lleno…), la CLI sigue funcionando.
    """
    try:
        setup_logging(AppPaths.from_environment().log_dir, console=False)
    except OSError as exc:
        print(f"Aviso: no se puede escribir el log ({exc})", file=sys.stderr)


def _error(message: object) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return EXIT_ERROR


def _cancelled() -> int:
    print("\nCancelado.", file=sys.stderr)
    return EXIT_CANCELLED


def _load_profiles(paths: AppPaths) -> ProfileSet:
    """Perfiles integrados y del usuario; los rotos se avisan y se ignoran."""
    profiles = load_profiles(paths.profiles_dir)
    for error in profiles.errors:
        print(f"Aviso: perfil ignorado: {error}", file=sys.stderr)
    return profiles


def _detect_wine() -> WineInstallation | None:
    """Detecta Wine; si no está, explica cómo instalarlo y devuelve ``None``."""
    installation = WineManager().detect()
    if installation is None:
        print(NO_WINE_MESSAGE, file=sys.stderr)
    return installation


# --- Comandos ------------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        analysis = analyze_game(args.path)
    except GameScanError as exc:
        return _error(exc)
    if args.json:
        print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(analysis))
    return EXIT_DETECTED if analysis.detection.detected else EXIT_NOT_DETECTED


def _check_data(
    analysis: GameAnalysis,
    profile: GameProfile | None,
    wine: WineInstallation | None,
    wine_error: str | None,
    checks: Sequence[RequirementCheck],
    ready: bool,
) -> dict[str, object]:
    """Resultado de ``check`` para ``--json``."""
    detection = analysis.detection
    data = {
        "game_path": str(analysis.path),
        "detected": detection.detected,
        "title": detection.details.get("title"),
        "profile": None,
        "wine": wine.description if wine else None,
        "wine_error": wine_error,
        "checks": [c.to_dict() for c in checks],
        "ready": ready,
    }
    if profile is not None:
        data["profile"] = {
            "id": profile.id,
            "name": profile.name,
            "status": profile.status.value,
            "notes": profile.notes,
            "save_dirs": list(profile.save_dirs),
            "known_issues": [
                {"id": i.id, "symptom": i.symptom, "solution": i.solution}
                for i in profile.known_issues
            ],
        }
    return data


def cmd_check(args: argparse.Namespace) -> int:
    try:
        analysis = analyze_game(args.path)
    except GameScanError as exc:
        return _error(exc)
    try:
        wine, wine_error = WineManager().detect(), None
    except WineError as exc:
        wine, wine_error = None, str(exc)
    paths = AppPaths.from_environment()
    profile = match_profile(analysis, _load_profiles(paths).profiles)
    detection = analysis.detection
    checks = check_requirements(analysis, HostSystem()) if detection.detected else ()
    bits = detection.details.get("bits")
    if detection.detected and wine is not None and bits in (32, 64):
        game_id = args.game_id or default_game_id(analysis)
        if not args.json:
            print(f"Comprobando que Wine ejecuta programas de {bits} bits…", file=sys.stderr)
        try:
            wine_check = check_wine_bits(
                PrefixManager(paths.prefixes_dir, wine),
                PrefixManager(paths.cache_dir / "probe", wine),
                game_id,
                bits,
            )
        except PrefixError as exc:
            return _error(exc)
        except KeyboardInterrupt:
            return _cancelled()
        checks = (*checks, wine_check)
    ready = detection.detected and wine is not None and not any(c.blocking for c in checks)
    code = EXIT_OK if ready else EXIT_NOT_DETECTED

    if args.json:
        data = _check_data(analysis, profile, wine, wine_error, checks, ready)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return code

    lines = [f"{APP_NAME} · comprobación", ""]

    def row(label: str, value: object) -> None:
        lines.append(f"  {label:<12} {value}")

    row("Carpeta:", analysis.path)
    if not detection.detected:
        row("Motor:", "no reconocido (por ahora solo se admite RPG Maker XP)")
    else:
        bits = detection.details.get("bits")
        about = [engine_display_name(detection.engine), detection.runtime]
        if bits:
            about.append(f"{bits} bits")
        row("Juego:", f"{detection.details.get('title') or analysis.path.name} "
                      f"({', '.join(about)})")  # fmt: skip
        if profile is not None:
            row("Perfil:", _profile_summary(profile))
            if profile.notes:
                row("", profile.notes)
        else:
            row("Perfil:", "ninguno (se usa la configuración por defecto)")
    if wine is not None:
        row("Wine:", wine.description)
    else:
        row("Wine:", wine_error or "no instalado")
        if wine_error is None:
            lines.append(f"             → {NO_WINE_MESSAGE}")

    if checks:
        lines += ["", "  Requisitos:", *format_checks(checks)]
    if profile is not None and profile.save_dirs:
        lines += ["", "  Partidas (dentro del prefijo de Wine del juego):"]
        lines += [f"    {p}" for p in profile.save_dirs]
    if profile is not None and profile.known_issues:
        lines += ["", "  Problemas conocidos:"]
        for issue in profile.known_issues:
            lines += [f"    - {issue.symptom}", f"      → {issue.solution}"]
    lines += ["", f"  Listo para jugar: {'sí' if ready else 'no'}"]
    print("\n".join(lines))
    return code


def cmd_profiles(args: argparse.Namespace) -> int:
    paths = AppPaths.from_environment()
    profiles = load_profiles(paths.profiles_dir)
    print(f"{APP_NAME} · perfiles\n")
    for profile in profiles.profiles:
        print(f"  {profile.id:<20} {_profile_summary(profile)}")
        print(f"  {'':<20} {profile.source}")
    if not profiles.profiles:
        print("  (ninguno)")
    print(f"\n  Tus perfiles van en {paths.profiles_dir}")
    if profiles.errors:
        print("\n  Ignorados por errores:")
        for error in profiles.errors:
            print(f"    - {error}")
        return EXIT_NOT_DETECTED
    return EXIT_OK


def cmd_wine(args: argparse.Namespace) -> int:
    try:
        wine = _detect_wine()
    except WineError as exc:
        return _error(exc)
    if wine is None:
        return EXIT_NOT_DETECTED

    print(f"{APP_NAME} · Wine\n")
    print(f"  {'Wine:':<12} {wine.wine}")
    print(f"  {'Versión:':<12} {wine.description}")
    print(f"  {'wineserver:':<12} {wine.wineserver or 'no encontrado'}")
    if not args.probe:
        return EXIT_OK

    print("\n  Comprobando qué programas ejecuta (prefijo temporal, unos segundos)…")
    prefixes = PrefixManager(AppPaths.from_environment().cache_dir / "probe", wine)
    game_id = f"comprobacion-{os.getpid()}"
    try:
        prefix = prefixes.create(game_id, "win64")
    except (PrefixError, WineError) as exc:
        return _error(f"no se pudo crear un prefijo: {exc}")
    except KeyboardInterrupt:
        return _cancelled()
    try:
        results = [prefixes.run_test_program(prefix, bits) for bits in (64, 32)]
    except KeyboardInterrupt:
        return _cancelled()
    finally:
        prefixes.delete(game_id)
    for result in results:
        print(f"  {f'{result.bits} bits:':<12} {'sí' if result.ok else 'NO'}")
    if not results[1].ok:
        print(f"\n  {MISSING_32_BIT_HINT}")
    return EXIT_OK if all(r.ok for r in results) else EXIT_NOT_DETECTED


def cmd_run(args: argparse.Namespace) -> int:
    try:
        wine = _detect_wine()
    except WineError as exc:
        return _error(exc)
    if wine is None:
        return EXIT_ERROR

    paths = AppPaths.from_environment()
    profiles = _load_profiles(paths)
    try:
        analysis = analyze_game(args.path)
    except GameScanError as exc:
        return _error(exc)

    if analysis.detection.detected:
        checks = check_requirements(analysis, HostSystem())
        if problems := format_checks(checks, only_problems=True):
            print("Requisitos del sistema:", *problems, "", sep="\n")
        if any(c.blocking for c in checks):
            if not args.ignore_checks:
                return _error(
                    "falta un requisito del sistema y el juego no funcionaría. "
                    "Resuélvelo o usa --ignore-checks para lanzarlo igualmente."
                )
            print("Se lanza igualmente (--ignore-checks).\n")

    prefixes = PrefixManager(paths.prefixes_dir, wine)
    print("Preparando el juego (la primera vez se crea su prefijo y tarda unos segundos)…")
    try:
        plan = prepare_launch(
            args.path,
            wine=wine,
            prefixes=prefixes,
            game_id=args.game_id,
            arch=args.arch,
            profiles=profiles.profiles,
            analysis=analysis,
        )
    except (GameScanError, LaunchError, PrefixError, WineError) as exc:
        return _error(exc)
    except KeyboardInterrupt:
        return _cancelled()  # PrefixManager ya ha borrado el prefijo a medias

    _print_plan(plan)
    print("Lanzando… (Ctrl+C para detenerlo)\n", flush=True)

    QCoreApplication.instance() or QCoreApplication([])
    processes = ProcessManager(log_dir=paths.log_dir)
    try:
        process = launch_game(plan, processes)
    except ProcessError as exc:
        return _error(exc)
    diagnoser = OutputDiagnoser(plan.profile)
    process.output.connect(lambda line: print(line, flush=True))
    process.output.connect(diagnoser.feed)

    # Qt no deja a Python atender Ctrl+C mientras espera: un temporizador le da paso.
    previous = signal.signal(signal.SIGINT, lambda *_: process.stop())
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(200)
    if args.timeout:
        QTimer.singleShot(int(args.timeout * 1000), process.stop)
    try:
        process.wait(2**31 - 1)
    finally:
        heartbeat.stop()
        signal.signal(signal.SIGINT, previous)

    outcome = process.outcome
    print(
        f"\nFin: {outcome.state.value}, código de salida {outcome.exit_code}, "
        f"{outcome.duration:.1f} s"
    )
    if outcome.error:
        print(f"  {outcome.error}")
    if outcome.log_file:
        print(f"  Log: {outcome.log_file}")
    if expected := [f for f in diagnoser.findings if f.issue.harmless]:
        print("\nMensajes esperados (no afectan al juego):", *format_findings(expected), sep="\n")
    if diagnoser.problems:
        print("\nProblemas detectados:", *format_findings(diagnoser.problems), sep="\n")
        for finding in diagnoser.problems:
            log.warning("%s: %s (%s)", plan.game_id, finding.issue.id, finding.line)
    if outcome.state is ProcessState.FINISHED and outcome.exit_code is not None:
        return outcome.exit_code if 0 <= outcome.exit_code <= 255 else EXIT_NOT_DETECTED
    return EXIT_NOT_DETECTED


def _print_plan(plan: LaunchPlan) -> None:
    print(f"  {'Juego:':<12} {plan.game_id}")
    if plan.profile is not None:
        print(f"  {'Perfil:':<12} {_profile_summary(plan.profile)}")
    print(f"  {'Ejecutable:':<12} {plan.executable}")
    print(f"  {'Prefijo:':<12} {plan.prefix.path} ({plan.prefix.arch})")
    for folder in plan.save_dirs:
        print(f"  {'Partidas:':<12} {folder}")


COMMANDS = {
    "analyze": cmd_analyze,
    "check": cmd_check,
    "wine": cmd_wine,
    "run": cmd_run,
    "profiles": cmd_profiles,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _ensure_utf8(sys.stdout)
    _setup_file_logging()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
