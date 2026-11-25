"""ProcessManager con procesos reales (el intérprete de Python), sin necesidad de Wine."""

import os
import sys
from pathlib import Path

import pytest

from pokemon_to_linux.infrastructure.wine.process_manager import (
    GameProcess,
    LaunchSpec,
    ProcessError,
    ProcessManager,
    ProcessState,
)

pytestmark = pytest.mark.integration

PY = Path(sys.executable)
# Python hijo sin búfer y en UTF-8 (en Windows usaría cp1252 al redirigir la salida).
CHILD_ENV = {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}


def spec(tmp_path, code: str, *, game_id="juego", env=None, stop_command=None):
    return LaunchSpec(
        game_id=game_id,
        program=PY,
        arguments=("-c", code),
        working_dir=tmp_path,
        environment={**os.environ, **CHILD_ENV, **(env or {})},
        stop_command=stop_command,
    )


def run(process: GameProcess, timeout_ms=15_000):
    lines = []
    process.output.connect(lines.append)
    process.start()
    assert process.wait(timeout_ms), "el proceso no terminó a tiempo"
    return lines


def test_output_exit_code_and_log(qapp, tmp_path):
    process = GameProcess(
        spec(tmp_path, "import sys; print('hola'); print('adiós', file=sys.stderr); sys.exit(3)"),
        log_dir=tmp_path / "logs",
    )
    lines = run(process)

    outcome = process.outcome
    assert outcome.state is ProcessState.FINISHED
    assert outcome.exit_code == 3
    assert outcome.duration > 0
    assert lines == ["hola", "adiós"]  # stdout y stderr juntos

    log = outcome.log_file.read_text(encoding="utf-8")
    assert outcome.log_file.parent == tmp_path / "logs" / "games" / "juego"
    assert "hola" in log
    assert "adiós" in log
    assert "código de salida 3" in log


def test_environment_and_working_dir(qapp, tmp_path):
    code = "import os; print(os.environ['PTL_PRUEBA']); print(os.getcwd())"
    process = GameProcess(spec(tmp_path, code, env={"PTL_PRUEBA": "valor"}))
    lines = run(process)

    assert lines[0] == "valor"
    assert Path(lines[1]).resolve() == tmp_path.resolve()


def test_partial_last_line_is_flushed(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "import sys; sys.stdout.write('sin salto')"))
    assert run(process) == ["sin salto"]


def test_program_that_does_not_exist(qapp, tmp_path):
    bad = LaunchSpec("juego", tmp_path / "no-existe", (), tmp_path, dict(os.environ))
    process = GameProcess(bad, log_dir=tmp_path / "logs")
    outcomes = []
    process.finished.connect(outcomes.append)
    process.start()
    process.wait(5000)

    assert len(outcomes) == 1  # una sola notificación
    assert outcomes[0].state is ProcessState.FAILED
    assert outcomes[0].error
    assert "failed" in outcomes[0].log_file.read_text(encoding="utf-8")


def test_missing_working_dir_raises(qapp, tmp_path):
    bad = LaunchSpec("juego", PY, (), tmp_path / "no-existe", {})
    with pytest.raises(ProcessError, match="carpeta de trabajo"):
        GameProcess(bad).start()


def test_cannot_start_twice(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "pass"))
    run(process)
    with pytest.raises(ProcessError, match="ya se inició"):
        process.start()


def test_stop_terminates_or_kills(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "import time; time.sleep(60)"), stop_grace_ms=300)
    process.start()
    assert process._process.waitForStarted(10_000)
    process.stop()

    assert process.wait(10_000)
    assert process.outcome.state is ProcessState.STOPPED


def test_stop_command_is_used(qapp, tmp_path):
    marker = tmp_path / "stop-ejecutado"
    stop = (str(PY), "-c", f"open({str(marker)!r}, 'w').close()")
    process = GameProcess(
        spec(tmp_path, "import time; time.sleep(60)", stop_command=stop), stop_grace_ms=300
    )
    process.start()
    assert process._process.waitForStarted(10_000)
    process.stop()
    process.wait(10_000)

    assert marker.exists()
    # El comando de parada no mata a este proceso Python: lo hace el margen de gracia.
    assert process.outcome.state is ProcessState.STOPPED


def test_stop_when_not_running_is_harmless(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "pass"))
    process.stop()
    assert process.state is ProcessState.NOT_STARTED


# --- ProcessManager -----------------------------------------------------------


def test_manager_tracks_running_games(qapp, tmp_path):
    manager = ProcessManager(stop_grace_ms=300)
    finished = []
    manager.finished.connect(finished.append)

    process = manager.launch(spec(tmp_path, "import time; time.sleep(60)", game_id="a"))
    assert manager.is_running("a")
    assert manager.active() == ("a",)

    with pytest.raises(ProcessError, match="ya se está ejecutando"):
        manager.launch(spec(tmp_path, "pass", game_id="a"))

    manager.stop_all()
    process.wait(10_000)

    assert not manager.is_running("a")
    assert [o.game_id for o in finished] == ["a"]


def test_manager_launch_error_does_not_leave_entry(qapp, tmp_path):
    manager = ProcessManager()
    bad = LaunchSpec("b", PY, (), tmp_path / "no-existe", {})

    with pytest.raises(ProcessError):
        manager.launch(bad)
    assert not manager.is_running("b")


def test_stop_game_use_case(qapp, tmp_path):
    from pokemon_to_linux.application.launch_game import stop_game

    manager = ProcessManager(stop_grace_ms=300)
    process = manager.launch(spec(tmp_path, "import time; time.sleep(60)", game_id="c"))
    assert process._process.waitForStarted(10_000)

    stop_game("c", manager)
    stop_game("no-existe", manager)  # parar un juego que no está en marcha no falla

    assert process.wait(10_000)
    assert process.outcome.state is ProcessState.STOPPED


# --- Logs, errores y estados poco frecuentes ------------------------------------


def test_logs_are_unique_and_pruned(qapp, tmp_path):
    logs = tmp_path / "logs"
    for _ in range(4):  # varios lanzamientos en el mismo segundo
        run(GameProcess(spec(tmp_path, "pass"), log_dir=logs, max_logs=3))

    files = sorted((logs / "games" / "juego").glob("*.log"))
    assert len(files) == 3  # solo se conservan los 3 más recientes
    assert len({f.name for f in files}) == 3


def test_unwritable_log_dir_does_not_prevent_launch(qapp, tmp_path):
    blocker = tmp_path / "no-es-carpeta"
    blocker.write_text("un fichero donde debería ir la carpeta de logs")
    process = GameProcess(spec(tmp_path, "print('sigo funcionando')"), log_dir=blocker)

    assert run(process) == ["sigo funcionando"]
    assert process.outcome.state is ProcessState.FINISHED
    assert process.outcome.log_file is None


def test_failing_stop_command_falls_back_to_kill(qapp, tmp_path):
    bad_stop = (str(tmp_path / "no-existe-wineserver"), "-k")
    process = GameProcess(
        spec(tmp_path, "import time; time.sleep(60)", stop_command=bad_stop), stop_grace_ms=300
    )
    process.start()
    assert process._process.waitForStarted(10_000)
    assert process.pid is not None

    process.stop()
    assert process.wait(10_000)
    assert process.outcome.state is ProcessState.STOPPED


@pytest.mark.skipif(sys.platform == "win32", reason="señales POSIX")
def test_crash_is_reported(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"))
    run(process)

    assert process.outcome.state is ProcessState.CRASHED
    assert process.outcome.exit_code is None


def test_wait_before_start(qapp, tmp_path):
    process = GameProcess(spec(tmp_path, "pass"))
    assert process.wait(100) is False
    assert process.pid is None
