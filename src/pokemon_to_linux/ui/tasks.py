"""Tareas en segundo plano para la interfaz.

Analizar una carpeta, ejecutar ``ldconfig`` o crear un prefijo de Wine
tarda: hecho en el hilo principal congelaría la ventana. ``TaskRunner``
ejecuta la función en el ``QThreadPool`` y entrega el resultado (o la
excepción) **en el hilo principal**, donde ya se puede tocar la interfaz y
la base de datos.

La entrega pasa por un método de ``TaskRunner``, que vive en el hilo
principal: así Qt encola la llamada. Si se conectara la señal del hilo de
trabajo directamente a una función de Python, Qt podría ejecutarla en ese
hilo.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from pokemon_to_linux.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

Callback = Callable[[Any], None]


class _Messenger(QObject):
    done = Signal(int, bool, object)  # id de la tarea, ¿bien?, resultado o excepción


class _Job(QRunnable):
    def __init__(self, task_id: int, fn: Callable[[], Any], messenger: _Messenger) -> None:
        super().__init__()
        self._id = task_id
        self._fn = fn
        self._messenger = messenger

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - se entrega al hilo principal
            self._messenger.done.emit(self._id, False, exc)
        else:
            self._messenger.done.emit(self._id, True, result)


class TaskRunner(QObject):
    """Ejecuta funciones en segundo plano; ``on_done``/``on_error`` van al hilo principal."""

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._messenger = _Messenger()
        self._messenger.done.connect(self._deliver)
        self._callbacks: dict[int, tuple[Callback, Callback | None, str]] = {}
        self._next_id = 0

    def run(
        self,
        fn: Callable[[], Any],
        on_done: Callback,
        on_error: Callback | None = None,
        *,
        name: str = "tarea",
    ) -> None:
        self._next_id += 1
        self._callbacks[self._next_id] = (on_done, on_error, name)
        self._pool.start(_Job(self._next_id, fn, self._messenger))

    @property
    def pending(self) -> int:
        """Tareas lanzadas cuyo resultado aún no se ha entregado."""
        return len(self._callbacks)

    def wait(self, timeout_ms: int = 30_000) -> bool:
        """Espera a que terminen las tareas (al cerrar la ventana)."""
        return self._pool.waitForDone(timeout_ms)

    @Slot(int, bool, object)
    def _deliver(self, task_id: int, ok: bool, value: object) -> None:
        on_done, on_error, name = self._callbacks.pop(task_id, (None, None, ""))
        if on_done is None:
            return
        if ok:
            on_done(value)
            return
        log.error("Falló la %s: %s", name, value, exc_info=value)
        if on_error is not None:
            on_error(value)
