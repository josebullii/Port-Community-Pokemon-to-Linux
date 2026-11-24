"""Clasificación de las DLL que importa un ejecutable de Windows.

Orden de clasificación, igual que el orden de búsqueda de Windows (la carpeta
del programa va antes que el sistema):

1. ``bundled``: está en la carpeta del juego.
2. ``system``: la trae Windows y Wine la implementa.
3. ``redistributable``: paquetes que se instalan aparte (Visual C++, DirectX,
   OpenAL…). Wine incluye versiones propias de muchas, pero no de todas.
4. ``missing``: ni está en la carpeta ni es conocida. El juego seguramente
   no arrancará.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# DLL que trae Windows (y que Wine implementa). En bloque de texto para que
# los 80+ nombres se puedan leer y revisar de un vistazo.
_SYSTEM_DLL_NAMES = """
    kernel32 kernelbase ntdll user32 gdi32 gdiplus advapi32 shell32 shlwapi shfolder
    ole32 oleaut32 olepro32 oleacc comctl32 comdlg32 winmm msacm32 ws2_32 wsock32
    mswsock dnsapi iphlpapi msvcrt ucrtbase imm32 setupapi cfgmgr32 version
    opengl32 glu32 dsound dinput dinput8 ddraw d3d8 d3d9 d3d10 d3d10_1 d3d11 d3d12
    dxgi dwrite d2d1 d3dcompiler_47 dwmapi uxtheme crypt32 bcrypt ncrypt secur32
    wintrust imagehlp dbghelp rpcrt4 userenv psapi netapi32 mpr wininet winhttp
    urlmon hid powrprof avrt mfplat mfreadwrite mf msimg32 usp10 riched20 riched32
    msftedit wtsapi32 xinput1_4 xinput9_1_0 xaudio2_8 xaudio2_9 normaliz msi
    ksuser mmdevapi propsys
"""
SYSTEM_DLLS = frozenset(f"{name}.dll" for name in _SYSTEM_DLL_NAMES.split()) | {"winspool.drv"}

_SYSTEM_PREFIXES = ("api-ms-win-", "ext-ms-win-")

REDISTRIBUTABLE_PATTERNS = (
    re.compile(r"^(msvcr|msvcp|vcruntime|vcomp|mfc|mfcm|concrt|vccorlib)\d+\w*\.dll$"),
    re.compile(r"^d3dx(9|10|11)_\d+\.dll$"),
    re.compile(r"^d3dcompiler_\d+\.dll$"),
    re.compile(r"^xinput1_[123]\.dll$"),
    re.compile(r"^xaudio2_[0-7]\.dll$"),
    re.compile(r"^(x3daudio|xapofx)1_\d+\.dll$"),
    re.compile(r"^openal32\.dll$"),
    re.compile(r"^physx\w*\.dll$"),
)


@dataclass(frozen=True, slots=True)
class DependencyReport:
    system: tuple[str, ...] = ()
    bundled: tuple[str, ...] = ()
    redistributable: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "system": list(self.system),
            "bundled": list(self.bundled),
            "redistributable": list(self.redistributable),
            "missing": list(self.missing),
        }


def is_system_dll(name: str) -> bool:
    name = name.lower()
    return name in SYSTEM_DLLS or name.startswith(_SYSTEM_PREFIXES)


def is_redistributable_dll(name: str) -> bool:
    """Redistribuible = encaja en los patrones *y* no viene ya con Windows."""
    name = name.lower()
    return not is_system_dll(name) and any(p.match(name) for p in REDISTRIBUTABLE_PATTERNS)


def classify_imports(imports: Iterable[str], bundled_files: Iterable[str]) -> DependencyReport:
    """Clasifica ``imports`` sabiendo qué ficheros hay junto al ejecutable."""
    local = {f.lower() for f in bundled_files}
    groups: dict[str, list[str]] = {k: [] for k in ("system", "bundled", "redist", "missing")}
    for name in dict.fromkeys(i.lower() for i in imports):  # sin duplicados, en orden
        if name in local:
            groups["bundled"].append(name)
        elif is_system_dll(name):
            groups["system"].append(name)
        elif is_redistributable_dll(name):
            groups["redist"].append(name)
        else:
            groups["missing"].append(name)
    return DependencyReport(
        system=tuple(groups["system"]),
        bundled=tuple(groups["bundled"]),
        redistributable=tuple(groups["redist"]),
        missing=tuple(groups["missing"]),
    )
