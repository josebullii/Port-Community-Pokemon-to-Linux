"""Caso de uso: ¿tiene el sistema lo que necesita este juego?

Comprobaciones (Wine y su soporte de 32 bits se comprueban aparte, con el
programa de prueba al crear el prefijo):

- **Sesión gráfica**: Wine necesita X11 (o XWayland).
- **OpenGL con los bits del juego**: Pokémon Z (mkxp-z) es de 32 bits e
  importa ``opengl32.dll``. Wine la implementa con la ``libGL.so.1`` de
  32 bits del sistema; sin ella, mkxp-z falla con *No matching GL pixel
  format available*. Comprobado en Ubuntu 24.04: ``wine32:i386`` no la
  instala si se usa ``--no-install-recommends``.
- **Sistema de ficheros**: en 9P (``/mnt/c`` de WSL) Pokémon Z tarda unos
  2,5 minutos en mostrar el título.
"""

from __future__ import annotations

from pokemon_to_linux.application.analyze_game import GameAnalysis
from pokemon_to_linux.domain.requirements import CheckStatus, RequirementCheck
from pokemon_to_linux.infrastructure.system.host import HostSystem

OPENGL_HINTS = {
    32: (
        "Instala OpenGL de 32 bits. Debian/Ubuntu: sudo apt install libgl1:i386 "
        "libgl1-mesa-dri:i386 · Fedora: sudo dnf install mesa-libGL.i686 "
        "mesa-dri-drivers.i686 · Arch: activa [multilib] y sudo pacman -S lib32-mesa. "
        "Con drivers propietarios de NVIDIA, instala también su versión de 32 bits."
    ),
    64: (
        "Instala OpenGL. Debian/Ubuntu: sudo apt install libgl1 libgl1-mesa-dri · "
        "Fedora: sudo dnf install mesa-libGL mesa-dri-drivers · Arch: sudo pacman -S mesa."
    ),
}

SLOW_FILESYSTEMS = {
    "9p": "carpeta de Windows compartida con WSL",
    "drvfs": "carpeta de Windows compartida con WSL",
    "cifs": "carpeta de red (SMB)",
    "smb3": "carpeta de red (SMB)",
    "nfs": "carpeta de red (NFS)",
    "nfs4": "carpeta de red (NFS)",
    "fuse.sshfs": "carpeta remota (SSHFS)",
}


def check_display(host: HostSystem) -> RequirementCheck:
    label = "Sesión gráfica"
    if display := host.x11_display:
        return RequirementCheck("display", label, CheckStatus.OK, f"X11 en {display}")
    if host.wayland_display:
        return RequirementCheck(
            "display",
            label,
            CheckStatus.WARNING,
            "Wayland sin X11 (DISPLAY no está definido)",
            "Wine necesita XWayland. Activa XWayland en tu escritorio.",
        )
    return RequirementCheck(
        "display",
        label,
        CheckStatus.ERROR,
        "No hay sesión gráfica (ni DISPLAY ni WAYLAND_DISPLAY)",
        "Lanza el juego desde el escritorio, no desde una consola sin pantalla.",
    )


def check_opengl(host: HostSystem, bits: int) -> RequirementCheck:
    label = f"OpenGL de {bits} bits"
    hint = OPENGL_HINTS[bits]
    has_gl = host.has_library("libGL.so.1", bits)
    if has_gl is None:
        return RequirementCheck(
            "opengl", label, CheckStatus.UNKNOWN, "No se puede comprobar (falta ldconfig)"
        )
    if not has_gl:
        return RequirementCheck(
            "opengl", label, CheckStatus.ERROR, f"No hay libGL.so.1 de {bits} bits", hint
        )
    # Con libglvnd, libGL.so.1 solo reparte: hace falta una biblioteca del
    # fabricante (libGLX_mesa.so.0, libGLX_nvidia.so.0…) de los mismos bits.
    if host.has_library("libGLX.so.0", bits):
        vendors = host.libraries_matching("libGLX_", ".so.0", bits) or []
        vendors = [v for v in vendors if v != "libGLX_indirect.so.0"]
        if not vendors:
            return RequirementCheck(
                "opengl",
                label,
                CheckStatus.ERROR,
                f"libGL.so.1 de {bits} bits sin driver (no hay libGLX_*.so.0)",
                hint,
            )
        names = ", ".join(v.removeprefix("libGLX_").removesuffix(".so.0") for v in vendors)
        return RequirementCheck("opengl", label, CheckStatus.OK, f"libGL.so.1 ({names})")
    return RequirementCheck("opengl", label, CheckStatus.OK, "libGL.so.1")


def check_filesystem(host: HostSystem, analysis: GameAnalysis) -> RequirementCheck:
    label = "Carpeta del juego"
    fstype = host.filesystem_type(analysis.path)
    if fstype is None:
        return RequirementCheck(
            "filesystem", label, CheckStatus.UNKNOWN, "No se puede saber el sistema de ficheros"
        )
    if fstype in SLOW_FILESYSTEMS:
        return RequirementCheck(
            "filesystem",
            label,
            CheckStatus.WARNING,
            f"Está en {SLOW_FILESYSTEMS[fstype]} ({fstype}): la carga será mucho más lenta",
            "Copia el juego a una carpeta de Linux (p. ej. ~/Juegos). En WSL, Pokémon Z "
            "tarda unos 2,5 minutos en mostrar el título desde /mnt/c.",
        )
    return RequirementCheck("filesystem", label, CheckStatus.OK, fstype)


def check_requirements(
    analysis: GameAnalysis, host: HostSystem | None = None
) -> tuple[RequirementCheck, ...]:
    host = host or HostSystem()
    details = analysis.detection.details
    checks = [check_display(host)]
    bits = details.get("bits")
    if details.get("requires_opengl") and bits in OPENGL_HINTS:
        checks.append(check_opengl(host, bits))
    checks.append(check_filesystem(host, analysis))
    return tuple(checks)
