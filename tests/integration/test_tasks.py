import threading

import pytest

from conftest import wait_until

pytestmark = pytest.mark.integration


@pytest.fixture
def runner(qapp):
    from pokemon_to_linux.ui.tasks import TaskRunner

    runner = TaskRunner()
    yield runner
    runner.wait()
    runner.deleteLater()


def test_result_is_delivered_in_the_main_thread(runner):
    main = threading.current_thread()
    seen = {}

    def work():
        seen["worker"] = threading.current_thread()
        return 42

    def done(value):
        seen["value"] = value
        seen["callback"] = threading.current_thread()

    runner.run(work, done)
    assert runner.pending == 1
    wait_until(lambda: "value" in seen)

    assert seen["value"] == 42
    assert seen["worker"] is not main
    assert seen["callback"] is main
    assert runner.pending == 0


def test_exception_goes_to_on_error_in_the_main_thread(runner):
    main = threading.current_thread()
    seen = {}

    def work():
        raise ValueError("fallo")

    def failed(exc):
        seen["exc"] = exc
        seen["callback"] = threading.current_thread()

    runner.run(work, lambda _: pytest.fail("no debía terminar bien"), failed)
    wait_until(lambda: "exc" in seen)

    assert isinstance(seen["exc"], ValueError)
    assert seen["callback"] is main


def test_exception_without_on_error_is_only_logged(runner, caplog):
    runner.run(lambda: 1 / 0, lambda _: None, name="división")
    wait_until(lambda: runner.pending == 0)

    assert "Falló la división" in caplog.text
