"""Interfaz de línea de comandos.

    pokemon-to-linux-cli analyze <carpeta> [--json]

Códigos de salida: 0 = motor detectado, 1 = no detectado, 2 = error de uso o ruta.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from pokemon_to_linux import APP_NAME, __version__
from pokemon_to_linux.application.analyze_game import (
    GameAnalysis,
    GameScanError,
    analyze_game,
    engine_display_name,
)

EXIT_DETECTED = 0
EXIT_NOT_DETECTED = 1
EXIT_ERROR = 2


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            text = f"{value:.0f}" if unit == "B" else f"{value:.1f}".replace(".", ",")
            return f"{text} {unit}"
        value /= 1024
    raise AssertionError  # pragma: no cover


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
    if d.executable:
        exe = d.executable
        if "architecture" in det:
            exe += f" ({det['architecture']}, {det['bits']} bits, {det['subsystem']})"
        row("Ejecutable:", exe)
    else:
        row("Ejecutable:", "no identificado")
    if "requires_opengl" in det:
        row("OpenGL:", "sí" if det["requires_opengl"] else "no")
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
    return parser


def _ensure_utf8(stream: TextIO) -> None:
    # En una tubería (p. ej. > fichero.json) Windows usaría cp1252: forzamos UTF-8.
    if hasattr(stream, "reconfigure") and not stream.isatty():
        stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _ensure_utf8(sys.stdout)

    if args.command == "analyze":
        try:
            analysis = analyze_game(args.path)
        except GameScanError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if args.json:
            print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(format_report(analysis))
        return EXIT_DETECTED if analysis.detection.detected else EXIT_NOT_DETECTED

    return EXIT_ERROR  # pragma: no cover  (argparse exige un comando)


if __name__ == "__main__":
    sys.exit(main())
