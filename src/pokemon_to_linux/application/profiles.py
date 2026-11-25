"""Aplicar perfiles de compatibilidad a un juego analizado."""

from __future__ import annotations

import getpass
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from pokemon_to_linux.application.analyze_game import GameAnalysis
from pokemon_to_linux.domain.profile import GAME_DIR, GameProfile, check_folder, select_profile

PUBLIC_USER = "public"

_FOLDERS = {
    "%USERPROFILE%": (),
    "%APPDATA%": ("AppData", "Roaming"),
    "%LOCALAPPDATA%": ("AppData", "Local"),
}


def match_profile(analysis: GameAnalysis, profiles: Sequence[GameProfile]) -> GameProfile | None:
    """El perfil que corresponde al juego analizado, si hay alguno."""
    detection = analysis.detection
    if not detection.detected:
        return None
    return select_profile(
        profiles,
        engine=detection.engine,
        runtime=detection.runtime,
        title=detection.details.get("title"),
        has_file=lambda f: analysis.scan.find_relative(f) is not None,
    )


def wine_user_dir(prefix_path: Path, user: str | None = None) -> Path:
    """``drive_c/users/<usuario>`` del prefijo (Wine usa el usuario de Linux)."""
    users = prefix_path / "drive_c" / "users"
    user = user or getpass.getuser()
    try:
        names = [d.name for d in users.iterdir() if d.is_dir() and d.name.lower() != PUBLIC_USER]
    except OSError:
        names = []
    if user not in names and len(names) == 1:
        user = names[0]
    return users / user


def resolve_folder(
    folder: str, *, prefix_path: Path, game_dir: Path, user: str | None = None
) -> Path:
    """``%USERPROFILE%/Saved Games/X`` → ruta real dentro del prefijo (o del juego)."""
    root, *rest = PurePosixPath(check_folder(folder, "carpeta")).parts
    if root == GAME_DIR:
        base = game_dir
    else:
        base = wine_user_dir(prefix_path, user).joinpath(*_FOLDERS[root])
    return base.joinpath(*rest)
