"""Detector de juegos RPG Maker XP (RGSS1), incluidos los que usan mkxp-z.

Nunca se decide por un solo fichero: cada indicio suma (o resta) a la
confianza y queda registrado como ``Evidence``. Para declarar el juego
detectado hace falta superar el umbral *y* tener al menos un indicio
específico de XP (datos ``.rxdata``, archivo ``.rgssad`` o RGSS1 en el INI).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import PureWindowsPath
from typing import Any

from pokemon_to_linux.engines.base import (
    DETECTION_THRESHOLD,
    DetectionResult,
    EngineDetector,
    Evidence,
)
from pokemon_to_linux.infrastructure.filesystem.game_scanner import GameScan
from pokemon_to_linux.infrastructure.filesystem.ini_reader import IniFile, IniReadError, read_ini
from pokemon_to_linux.infrastructure.filesystem.pe_inspector import (
    NotPEError,
    find_markers,
    parse_pe,
    read_binary,
)

ENGINE_ID = "rpgmaker_xp"

RGSS1_DLL = re.compile(r"^rgss1\d\d[a-z]?\.dll$", re.IGNORECASE)
RGSS2_DLL = re.compile(r"^rgss2\d\d[a-z]?\.dll$", re.IGNORECASE)  # RPG Maker VX
RGSS3_DLL = re.compile(r"^rgss3\d\d[a-z]?\.dll$", re.IGNORECASE)  # RPG Maker VX Ace

RGSS_NAME = re.compile(r"^rgss(?P<major>\d)(?P<minor>\d\d)(?P<edition>[a-z]?)\.dll$", re.IGNORECASE)
EDITIONS = {"e": "inglesa", "j": "japonesa"}
MKXP_RUNTIMES = ("mkxp-z", "mkxp")


def parse_rgss_name(name: str) -> dict[str, str] | None:
    """``RGSS104E.dll`` → ``{"version": "1.04", "edition": "inglesa"}``."""
    match = RGSS_NAME.match(name)
    if match is None:
        return None
    edition = match["edition"].lower()
    return {
        "version": f"{match['major']}.{match['minor']}",
        "edition": EDITIONS.get(edition, f"desconocida ({edition})" if edition else "sin indicar"),
    }


RUNTIME_MARKERS = {
    "mkxp_z": re.compile(rb"mkxp-z"),
    "mkxp": re.compile(rb"mkxp"),
    "sdl2_version": re.compile(rb"SDL2-(\d+\.\d+\.\d+)"),
}

# Pesos de los indicios a favor (suman 1.0 como máximo).
W_INI_SECTION = 0.10
W_INI_LIBRARY = 0.25
W_INI_SCRIPTS = 0.15
W_DLL_ON_DISK = 0.15
W_XP_DATA = 0.25
W_RESOURCES = 0.05
W_EXECUTABLE = 0.05
# Indicios en contra (otros motores RPG Maker).
W_OTHER_ENGINE = -0.30


class RPGMakerXPDetector(EngineDetector):
    engine_id = ENGINE_ID
    display_name = "RPG Maker XP"

    def detect(self, scan: GameScan) -> DetectionResult:
        evidence: list[Evidence] = []
        warnings: list[str] = []
        details: dict[str, Any] = {}
        xp_specific = False

        def add(indicator: str, detail: str, weight: float) -> None:
            evidence.append(Evidence(indicator, detail, weight))

        # --- Game.ini ---------------------------------------------------
        ini = self._read_game_ini(scan, warnings)
        library = scripts = None
        if ini is not None and ini.has_section("Game"):
            add("game_ini", f"{ini.path.name} con sección [Game]", W_INI_SECTION)
            details["title"] = ini.get("Game", "Title") or None
            details["ini_encoding"] = ini.encoding
            library = ini.get("Game", "Library") or None
            scripts = ini.get("Game", "Scripts") or None
            details["ini_library"] = library
            details["ini_scripts"] = scripts
            rtp = [v for k in ("RTP1", "RTP2", "RTP3") if (v := ini.get("Game", k))]
            details["rtp"] = rtp

            if library:
                lib_name = PureWindowsPath(library).name
                if RGSS1_DLL.match(lib_name):
                    add("ini_library", f"Library={library} (RGSS1)", W_INI_LIBRARY)
                    xp_specific = True
                elif RGSS2_DLL.match(lib_name) or RGSS3_DLL.match(lib_name):
                    add("ini_library", f"Library={library} (no es RGSS1)", W_OTHER_ENGINE)
            if scripts and scripts.lower().endswith(".rxdata"):
                add("ini_scripts", f"Scripts={scripts}", W_INI_SCRIPTS)
                xp_specific = True
            if rtp:
                warnings.append(
                    "El juego usa un RTP de RPG Maker XP ("
                    + ", ".join(rtp)
                    + "). Hay que instalarlo aparte desde su fuente oficial."
                )

        # --- DLL del runtime en disco -------------------------------------
        dlls = scan.files_with_suffix(".dll")
        rgss1 = [d for d in dlls if RGSS1_DLL.match(d)]
        details["rgss_dlls"] = rgss1
        if rgss1:
            add("rgss1_dll", ", ".join(rgss1), W_DLL_ON_DISK)
        other_rgss = [d for d in dlls if RGSS2_DLL.match(d) or RGSS3_DLL.match(d)]

        # --- Datos del juego ----------------------------------------------
        rxdata = scan.files_with_suffix(".rxdata", directory="Data")
        archive = scan.find_file("Game.rgssad")
        details["rxdata_files"] = len(rxdata)
        if rxdata or archive:
            parts = []
            if rxdata:
                parts.append(f"{len(rxdata)} ficheros .rxdata en Data/")
            if archive:
                parts.append(f"archivo cifrado {archive}")
            add("xp_data", "; ".join(parts), W_XP_DATA)
            xp_specific = True

        other_data = (
            scan.extension_counts.get(".rvdata", 0)
            + scan.extension_counts.get(".rvdata2", 0)
            + (1 if scan.find_file("Game.rgss2a") or scan.find_file("Game.rgss3a") else 0)
        )
        if other_rgss or other_data:
            add(
                "other_rpg_maker",
                "indicios de RPG Maker VX / VX Ace (RGSS2/RGSS3, .rvdata, .rgss2a/.rgss3a)",
                W_OTHER_ENGINE,
            )
            warnings.append(
                "Hay indicios de RPG Maker VX o VX Ace. Ese motor todavía no está soportado."
            )

        if scan.find_dir("Graphics") and scan.find_dir("Audio"):
            add("resources", "carpetas Graphics/ y Audio/", W_RESOURCES)

        # --- Ejecutable y runtime -----------------------------------------
        executable = self._choose_executable(scan, ini, warnings, details)
        runtime = "unknown"
        if executable is not None:
            runtime = self._inspect_executable(scan, executable, add, warnings, details)

        if runtime == "unknown" and rgss1 and xp_specific:
            runtime = "rgss1"
        details["mkxp_config"] = scan.find_file("mkxp.json") is not None
        details["preload_script"] = scan.find_file("preload.rb") is not None

        # Archivo de scripts indicado en el INI.
        if scripts and not archive and scan.find_relative(scripts) is None:
            warnings.append(
                f"No se encuentra el archivo de scripts indicado en Game.ini: {scripts}"
            )

        # DLL RGSS: versión (del nombre), validez y arquitectura (de la cabecera PE).
        lib_name = PureWindowsPath(library).name if library else ""
        lib_rel = (scan.find_relative(library) or scan.find_file(lib_name)) if library else None
        dll_infos = [self._inspect_rgss_dll(scan, rel) for rel in rgss1]
        if lib_rel and RGSS1_DLL.match(lib_name) and lib_rel not in rgss1:
            dll_infos.append(self._inspect_rgss_dll(scan, lib_rel))  # p. ej. System/RGSS…
        details["rgss_dll_info"] = dll_infos
        if (lib_version := parse_rgss_name(lib_name)) is not None:
            details["rgss_library_version"] = lib_version["version"]

        # Solo importa si el runtime carga la DLL (mkxp-z no la usa).
        if library and RGSS1_DLL.match(lib_name) and runtime not in MKXP_RUNTIMES:
            lib_info = next((i for i in dll_infos if i["path"] == lib_rel), None)
            exe_arch = details.get("architecture")
            if lib_info is None:
                warnings.append(
                    f"Game.ini indica {library}, pero esa DLL no está en la carpeta del juego."
                )
            elif not lib_info["valid"]:
                warnings.append(f"{lib_info['name']} no es una DLL válida: {lib_info['error']}")
            elif exe_arch and lib_info["architecture"] != exe_arch:
                warnings.append(
                    f"{lib_info['name']} es {lib_info['architecture']} y {executable} es "
                    f"{exe_arch}: no pueden funcionar juntos."
                )

        confidence = max(0.0, min(1.0, sum(e.weight for e in evidence)))
        detected = confidence >= DETECTION_THRESHOLD and xp_specific

        return DetectionResult(
            engine=ENGINE_ID,
            detected=detected,
            confidence=round(confidence, 4),
            executable=executable,
            runtime=runtime,
            warnings=tuple(warnings),
            evidence=tuple(evidence),
            details=details,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _read_game_ini(scan: GameScan, warnings: list[str]) -> IniFile | None:
        name = scan.find_file("Game.ini")
        if name is None:
            return None
        try:
            return read_ini(scan.path_of(name))
        except IniReadError as exc:
            warnings.append(f"No se ha podido leer Game.ini: {exc}")
            return None

    @staticmethod
    def _inspect_rgss_dll(scan: GameScan, relative: str) -> dict[str, Any]:
        name = relative.rsplit("/", 1)[-1]
        info: dict[str, Any] = {"name": name, "path": relative}
        info.update(parse_rgss_name(name) or {})
        try:
            pe = parse_pe(read_binary(scan.path_of(relative)))
        except NotPEError as exc:
            info.update(valid=False, architecture=None, error=str(exc))
            return info
        info.update(architecture=pe.machine, bits=pe.bits, valid=pe.is_dll)
        info["error"] = None if pe.is_dll else "es un ejecutable, no una DLL"
        return info

    @staticmethod
    def _choose_executable(
        scan: GameScan, ini: IniFile | None, warnings: list[str], details: dict[str, Any]
    ) -> str | None:
        executables = list(scan.files_with_suffix(".exe"))
        chosen: str | None = None
        # El reproductor de RPG Maker lee el INI con su mismo nombre base.
        if ini is not None:
            stem = ini.path.stem.lower()
            chosen = next((e for e in executables if e.lower() == f"{stem}.exe"), None)
        if chosen is None:
            chosen = next((e for e in executables if e.lower() == "game.exe"), None)
        if chosen is None and len(executables) == 1:
            chosen = executables[0]

        others = [e for e in executables if e != chosen]
        details["other_executables"] = others
        if chosen is None and executables:
            warnings.append(
                "Hay varios ejecutables y ninguno se llama Game.exe: "
                + ", ".join(executables)
                + ". Elige el correcto manualmente."
            )
        elif others:
            warnings.append(
                f"Además de {chosen} hay otros ejecutables: {', '.join(others)}. Se usará {chosen}."
            )
        return chosen

    @staticmethod
    def _inspect_executable(
        scan: GameScan,
        executable: str,
        add: Callable[[str, str, float], None],
        warnings: list[str],
        details: dict[str, Any],
    ) -> str:
        try:
            data = read_binary(scan.path_of(executable))
            info = parse_pe(data)
        except NotPEError as exc:
            warnings.append(f"{executable} no es un ejecutable de Windows válido: {exc}")
            return "unknown"

        add("executable", f"{executable} ({info.machine}, {info.bits} bits)", W_EXECUTABLE)
        details["architecture"] = info.machine
        details["bits"] = info.bits
        details["subsystem"] = info.subsystem
        details["imports"] = list(info.imports)
        details["requires_opengl"] = info.imports_dll("opengl32.dll")
        if info.is_dll:
            warnings.append(f"{executable} es una DLL, no un programa.")

        markers = find_markers(data, RUNTIME_MARKERS)
        if "sdl2_version" in markers:
            details["sdl2_version"] = markers["sdl2_version"]
        if "mkxp_z" in markers:
            add("runtime", f"{executable} es mkxp-z", 0.0)
            return "mkxp-z"
        if "mkxp" in markers:
            add("runtime", f"{executable} es mkxp", 0.0)
            return "mkxp"
        return "unknown"
