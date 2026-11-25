"""Casos de uso de la biblioteca: añadir, quitar, consultar y registrar partidas.

Reparto entre hilos (la interfaz no debe bloquearse):

- ``analyze_game`` e ``inspect_game`` recorren la carpeta del juego y
  ejecutan ``ldconfig``: van en un hilo de trabajo. No tocan la base de datos.
- ``Library`` usa la conexión SQLite, que solo vale en el hilo que la abrió:
  se llama desde el hilo principal con el resultado ya calculado.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pokemon_to_linux.application.analyze_game import GameAnalysis, GameScanError, analyze_game
from pokemon_to_linux.application.check_requirements import check_requirements
from pokemon_to_linux.application.diagnose_output import Finding
from pokemon_to_linux.application.launch_game import default_game_id
from pokemon_to_linux.application.profiles import match_profile, resolve_folder
from pokemon_to_linux.domain.game import Game, LaunchRecord
from pokemon_to_linux.domain.profile import GameProfile
from pokemon_to_linux.domain.requirements import RequirementCheck
from pokemon_to_linux.infrastructure.database.game_repository import (
    DuplicateGameError,
    GameRepository,
)
from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.system.host import HostSystem
from pokemon_to_linux.infrastructure.wine.prefix_manager import read_prefix_arch
from pokemon_to_linux.infrastructure.wine.process_manager import LaunchOutcome

log = get_logger(__name__)

MAX_NAME = 120


class LibraryError(RuntimeError):
    """No se puede hacer lo que se ha pedido. El mensaje es para el usuario."""


def _now() -> datetime:
    return datetime.now(UTC)


class Library:
    def __init__(self, repository: GameRepository, clock: Callable[[], datetime] = _now) -> None:
        self._repo = repository
        self._clock = clock

    def games(self) -> list[Game]:
        return self._repo.list()

    def get(self, game_id: str) -> Game | None:
        return self._repo.get(game_id)

    def add(self, analysis: GameAnalysis) -> Game:
        """Añade un juego ya analizado (``analyze_game``)."""
        detection = analysis.detection
        if not detection.detected:
            raise LibraryError(
                f"No se reconoce el motor del juego en {analysis.path}. Por ahora solo se "
                "admiten juegos de RPG Maker XP (la carpeta debe tener Game.exe, Game.ini "
                "y Data/)."
            )
        path = analysis.path.resolve()
        if (existing := self._repo.get_by_path(path)) is not None:
            raise LibraryError(f"Esa carpeta ya está en la biblioteca como «{existing.name}».")
        details = detection.details
        name = (details.get("title") or path.name).strip()[:MAX_NAME] or path.name
        game = Game(
            id=self._free_id(default_game_id(analysis)),
            name=name,
            path=path,
            engine=detection.engine,
            runtime=detection.runtime,
            bits=details.get("bits"),
            added_at=self._clock(),
        )
        try:
            added = self._repo.add(game)
        except DuplicateGameError as exc:
            raise LibraryError(str(exc)) from exc
        log.info("Juego añadido a la biblioteca: %s (%s)", added.id, added.path)
        return added

    def _free_id(self, base: str) -> str:
        """``base``, o ``base-2``, ``base-3``… si ya lo usa otro juego.

        Dos copias del mismo juego (p. ej. dos versiones) no deben compartir
        prefijo: cada una tendría las partidas de la otra.
        """
        candidate, n = base, 1
        while self._repo.get(candidate) is not None:
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    def rename(self, game_id: str, name: str) -> Game:
        name = name.strip()
        if not name:
            raise LibraryError("El nombre no puede estar vacío.")
        self._repo.rename(game_id, name[:MAX_NAME])
        return self._require(game_id)

    def remove(self, game_id: str) -> None:
        """Quita el juego de la biblioteca. Su carpeta y su prefijo (con las partidas) quedan."""
        if not self._repo.remove(game_id):
            raise LibraryError(f"No hay ningún juego {game_id} en la biblioteca.")
        log.info("Juego quitado de la biblioteca: %s", game_id)

    def record_launch(
        self, game_id: str, outcome: LaunchOutcome, problems: Sequence[Finding] = ()
    ) -> LaunchRecord:
        record = LaunchRecord(
            game_id=game_id,
            started_at=self._clock() - timedelta(seconds=outcome.duration),
            duration=outcome.duration,
            state=outcome.state.value,
            exit_code=outcome.exit_code,
            error=outcome.error,
            log_file=outcome.log_file,
            problems=tuple(dict.fromkeys(f.issue.id for f in problems)),
        )
        self._repo.record_launch(record)
        return record

    def history(self, game_id: str, limit: int = 20) -> Sequence[LaunchRecord]:
        return self._repo.launches(game_id, limit)

    def _require(self, game_id: str) -> Game:
        if (game := self._repo.get(game_id)) is None:
            raise LibraryError(f"No hay ningún juego {game_id} en la biblioteca.")
        return game


@dataclass(frozen=True, slots=True)
class GameDetails:
    """Lo que la pantalla de detalles muestra de un juego, calculado sin la base de datos."""

    game: Game
    analysis: GameAnalysis | None
    error: str | None
    """Si la carpeta ya no existe o no se puede leer."""
    profile: GameProfile | None = None
    checks: tuple[RequirementCheck, ...] = ()
    prefix_path: Path | None = None
    """El prefijo del juego, si ya se ha creado."""
    save_dirs: tuple[Path, ...] = ()
    """Carpetas de partidas reales (solo si el prefijo existe)."""

    @property
    def ready(self) -> bool:
        return (
            self.error is None
            and self.analysis is not None
            and not any(c.blocking for c in self.checks)
        )


def inspect_game(
    game: Game,
    *,
    profiles: Sequence[GameProfile],
    prefixes_dir: Path,
    host: HostSystem | None = None,
) -> GameDetails:
    """Analiza la carpeta del juego y comprueba los requisitos. Tarda: va en un hilo."""
    try:
        analysis = analyze_game(game.path)
    except GameScanError as exc:
        return GameDetails(game, None, f"No se puede leer la carpeta del juego: {exc}")
    if not analysis.detection.detected:
        return GameDetails(
            game, analysis, "La carpeta ya no contiene un juego reconocible (¿se ha movido?)."
        )
    profile = match_profile(analysis, profiles)
    checks = check_requirements(analysis, host)
    prefix_path = prefixes_dir / game.id
    if read_prefix_arch(prefix_path) is None:
        return GameDetails(game, analysis, None, profile, checks)
    save_dirs = tuple(
        resolve_folder(p, prefix_path=prefix_path, game_dir=game.path)
        for p in (profile.save_dirs if profile else ())
    )
    return GameDetails(game, analysis, None, profile, checks, prefix_path, save_dirs)
