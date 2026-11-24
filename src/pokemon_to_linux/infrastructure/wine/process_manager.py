"""Ejecución de juegos con ``QProcess``, sin bloquear la interfaz.

- La salida (stdout + stderr) se emite línea a línea y se guarda en un log
  por lanzamiento: ``<log_dir>/games/<id>/<fecha>.log``.
- Se registran código de salida, duración y errores.
- Para parar un juego de Wine no basta con terminar el proceso ``wine``:
  el juego vive bajo ``wineserver``. ``stop_command`` (``wineserver -k``)
  cierra todo el prefijo; si el proceso sigue vivo tras un margen, se mata.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TextIO

from PySide6.QtCore import QEventLoop, QObject, QProcess, QProcessEnvironment, QTimer, Signal

from pokemon_to_linux.infrastructure.logging.logger import get_logger
from pokemon_to_linux.infrastructure.wine.wine_manager import WineError, run_command

log = get_logger(__name__)


class ProcessError(RuntimeError):
    pass


class ProcessState(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    STOPPING = "stopping"
    FINISHED = "finished"
    """Terminó por sí mismo (con cualquier código de salida)."""
    CRASHED = "crashed"
    STOPPED = "stopped"
    """Lo paramos nosotros."""
    FAILED = "failed"
    """No llegó a arrancar."""


@dataclass(frozen=True, slots=True)
class LaunchSpec:
    game_id: str
    program: Path
    arguments: tuple[str, ...]
    working_dir: Path
    environment: Mapping[str, str] = field(default_factory=dict)
    stop_command: tuple[str, ...] | None = None
    """Comando para cerrar el juego y sus hijos (p. ej. ``wineserver -k``)."""


@dataclass(frozen=True, slots=True)
class LaunchOutcome:
    game_id: str
    state: ProcessState
    exit_code: int | None
    duration: float
    error: str | None = None
    log_file: Path | None = None


class GameProcess(QObject):
    started = Signal()
    output = Signal(str)
    finished = Signal(object)  # LaunchOutcome

    def __init__(
        self,
        spec: LaunchSpec,
        *,
        log_dir: Path | None = None,
        stop_grace_ms: int = 5000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.spec = spec
        self.state = ProcessState.NOT_STARTED
        self.outcome: LaunchOutcome | None = None
        self.log_file: Path | None = None
        self._log_dir = log_dir
        self._grace_ms = stop_grace_ms
        self._buffer = ""
        self._started_at = 0.0
        self._log: TextIO | None = None
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

    # --- API ----------------------------------------------------------------

    def start(self) -> None:
        if self.state is not ProcessState.NOT_STARTED:
            raise ProcessError(f"{self.spec.game_id}: el proceso ya se inició")
        if not self.spec.working_dir.is_dir():
            raise ProcessError(f"La carpeta de trabajo no existe: {self.spec.working_dir}")

        env = QProcessEnvironment()
        for key, value in self.spec.environment.items():
            env.insert(key, value)
        self._process.setProgram(str(self.spec.program))
        self._process.setArguments(list(self.spec.arguments))
        self._process.setWorkingDirectory(str(self.spec.working_dir))
        self._process.setProcessEnvironment(env)

        self._open_log()
        self._started_at = time.monotonic()
        self.state = ProcessState.RUNNING
        log.info("Lanzando %s: %s %s", self.spec.game_id, self.spec.program,
                 " ".join(self.spec.arguments))  # fmt: skip
        self._process.start()

    def stop(self) -> None:
        """Cierre controlado: ``stop_command`` y, si no basta, matar el proceso."""
        if self.state is not ProcessState.RUNNING:
            return
        self.state = ProcessState.STOPPING
        self._write_log(f"--- Deteniendo {self.spec.game_id} ---")
        if self.spec.stop_command:
            try:
                run_command(self.spec.stop_command, self.spec.environment, 30)
            except WineError as exc:
                log.warning("No se pudo ejecutar %s: %s", self.spec.stop_command[0], exc)
        else:
            self._process.terminate()
        QTimer.singleShot(self._grace_ms, self._kill_if_running)

    def wait(self, timeout_ms: int = 30_000) -> bool:
        """Espera a que termine (para la CLI y las pruebas, no para la interfaz).

        Usa un bucle de eventos propio y no ``waitForFinished``: así siguen
        funcionando los temporizadores (p. ej. el cierre forzado de ``stop``).
        """
        if self.outcome is not None:
            return True
        if self.state is ProcessState.NOT_STARTED:
            return False
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self.finished.connect(loop.quit)
        timer.start(timeout_ms)
        if self.outcome is None:  # pudo terminar mientras se preparaba el bucle
            loop.exec()
        timer.stop()
        self.finished.disconnect(loop.quit)
        return self.outcome is not None

    @property
    def pid(self) -> int | None:
        pid = self._process.processId()
        return pid or None

    # --- Señales de QProcess ---------------------------------------------------

    def _on_started(self) -> None:
        self.started.emit()

    def _on_output(self) -> None:
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buffer += data.replace("\r\n", "\n")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            self._emit_line(line)

    def _on_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        if self._buffer:
            self._emit_line(self._buffer)
            self._buffer = ""
        if self.state is ProcessState.STOPPING:
            state = ProcessState.STOPPED
        elif status == QProcess.ExitStatus.CrashExit:
            state = ProcessState.CRASHED
        else:
            state = ProcessState.FINISHED
        code = exit_code if status == QProcess.ExitStatus.NormalExit else None
        self._finish(state, code, None)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._finish(ProcessState.FAILED, None, self._process.errorString())

    # --- Internos --------------------------------------------------------------

    def _kill_if_running(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            log.warning("%s no se cerró a tiempo: se fuerza el cierre", self.spec.game_id)
            self._process.kill()

    def _emit_line(self, line: str) -> None:
        self._write_log(line)
        self.output.emit(line)

    def _finish(self, state: ProcessState, code: int | None, error: str | None) -> None:
        if self.outcome is not None:
            return  # FailedToStart puede llegar junto con finished
        duration = time.monotonic() - self._started_at if self._started_at else 0.0
        self.state = state
        self.outcome = LaunchOutcome(self.spec.game_id, state, code, duration, error, self.log_file)
        summary = f"--- Fin: {state.value}, código de salida {code}, {duration:.1f} s ---"
        if error:
            summary += f" ({error})"
        self._write_log(summary)
        self._close_log()
        log_fn = log.warning if state in (ProcessState.FAILED, ProcessState.CRASHED) else log.info
        log_fn("%s terminó: %s, código %s, %.1f s%s", self.spec.game_id, state.value, code,
               duration, f" ({error})" if error else "")  # fmt: skip
        self.finished.emit(self.outcome)

    def _open_log(self) -> None:
        if self._log_dir is None:
            return
        folder = self._log_dir / "games" / self.spec.game_id
        try:
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_file = folder / f"{stamp}.log"
            self._log = self.log_file.open("a", encoding="utf-8")
        except OSError as exc:
            log.warning("No se puede crear el log de %s: %s", self.spec.game_id, exc)
            self.log_file = None
            return
        wine_vars = {k: v for k, v in self.spec.environment.items() if k.startswith("WINE")}
        self._write_log(f"--- {self.spec.game_id} · {datetime.now().isoformat(timespec='seconds')}")
        self._write_log(f"Programa: {self.spec.program}")
        self._write_log(f"Argumentos: {list(self.spec.arguments)}")
        self._write_log(f"Carpeta: {self.spec.working_dir}")
        self._write_log(f"Entorno Wine: {wine_vars}")
        self._write_log("---")

    def _write_log(self, line: str) -> None:
        if self._log is not None:
            self._log.write(line + "\n")
            self._log.flush()

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None


class ProcessManager(QObject):
    """Mantiene referencias a los juegos en ejecución (uno por ``game_id``)."""

    finished = Signal(object)  # LaunchOutcome

    def __init__(
        self,
        *,
        log_dir: Path | None = None,
        stop_grace_ms: int = 5000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._log_dir = log_dir
        self._grace_ms = stop_grace_ms
        self._active: dict[str, GameProcess] = {}

    def launch(self, spec: LaunchSpec) -> GameProcess:
        if spec.game_id in self._active:
            raise ProcessError(f"{spec.game_id} ya se está ejecutando")
        process = GameProcess(spec, log_dir=self._log_dir, stop_grace_ms=self._grace_ms,
                              parent=self)  # fmt: skip
        process.finished.connect(self._on_finished)
        self._active[spec.game_id] = process
        try:
            process.start()
        except ProcessError:
            del self._active[spec.game_id]
            raise
        return process

    def stop(self, game_id: str) -> None:
        if (process := self._active.get(game_id)) is not None:
            process.stop()

    def stop_all(self) -> None:
        for process in list(self._active.values()):
            process.stop()

    def is_running(self, game_id: str) -> bool:
        return game_id in self._active

    def active(self) -> Sequence[str]:
        return tuple(self._active)

    def _on_finished(self, outcome: LaunchOutcome) -> None:
        process = self._active.pop(outcome.game_id, None)
        if process is not None:
            process.deleteLater()
        self.finished.emit(outcome)
