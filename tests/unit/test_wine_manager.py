import os
import sys

import pytest

from pokemon_to_linux.infrastructure.wine.wine_manager import (
    CommandResult,
    WineError,
    WineManager,
    WineTimeoutError,
    parse_version,
    run_command,
    wine_environment,
)

UBUNTU = "wine-9.0 (Ubuntu 9.0~repack-4build3)\n"
OK = CommandResult(0, UBUNTU)


def make_executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


class FakeRunner:
    def __init__(self, result=OK):
        self.result = result
        self.calls = []

    def __call__(self, args, env, timeout, cwd):
        self.calls.append(list(args))
        return self.result


# --- Versiones ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "version", "flavor"),
    [
        (UBUNTU, "9.0", "Ubuntu 9.0~repack-4build3"),
        ("wine-8.0.2\n", "8.0.2", None),
        ("wine-9.21 (Staging)", "9.21", "Staging"),
        ("wine-10.0-rc1", "10.0-rc1", None),
    ],
)
def test_parse_version(text, version, flavor):
    assert parse_version(text) == (version, flavor)


@pytest.mark.parametrize("text", ["", "Wine 9.0", "error: algo"])
def test_parse_version_rejects_garbage(text):
    with pytest.raises(WineError, match="no reconocida"):
        parse_version(text)


# --- Detección --------------------------------------------------------------


def test_detect_from_path(tmp_path):
    wine = make_executable(tmp_path / "bin" / "wine")
    server = make_executable(tmp_path / "bin" / "wineserver")
    runner = FakeRunner()
    manager = WineManager(runner=runner, which=lambda n: str(wine) if n == "wine" else None)

    inst = manager.detect()

    assert inst.wine == wine
    assert inst.wineserver == server
    assert inst.version == "9.0"
    assert inst.version_tuple == (9, 0)
    assert inst.flavor == "Ubuntu 9.0~repack-4build3"
    assert inst.description == "wine-9.0 (Ubuntu 9.0~repack-4build3)"
    assert runner.calls == [[str(wine), "--version"]]


@pytest.mark.skipif(sys.platform == "win32", reason="permisos de ejecución POSIX")
def test_detect_from_known_location_outside_path(tmp_path):
    """Ubuntu con solo wine64: /usr/lib/wine/wine64 no está en el PATH."""
    wine64 = make_executable(tmp_path / "lib" / "wine64")
    server = make_executable(tmp_path / "lib" / "wineserver")
    manager = WineManager(runner=FakeRunner(), which=lambda _n: None, known_locations=[str(wine64)])

    inst = manager.detect()

    assert inst.wine == wine64
    assert inst.wineserver == server


@pytest.mark.skipif(sys.platform == "win32", reason="permisos de ejecución POSIX")
def test_wineserver_found_via_path_when_not_sibling(tmp_path):
    wine = make_executable(tmp_path / "a" / "wine")
    server = make_executable(tmp_path / "b" / "wineserver")
    manager = WineManager(
        runner=FakeRunner(),
        which=lambda n: {"wine": str(wine), "wineserver": str(server)}.get(n),
    )

    assert manager.detect().wineserver == server


def test_detect_returns_none_without_wine():
    manager = WineManager(runner=FakeRunner(), which=lambda _n: None, known_locations=[])
    assert manager.detect() is None


@pytest.mark.skipif(sys.platform == "win32", reason="permisos de ejecución POSIX")
def test_explicit_path(tmp_path):
    wine = make_executable(tmp_path / "mi-wine")
    manager = WineManager(wine, runner=FakeRunner(), which=lambda _n: None)

    assert manager.detect().wine == wine
    assert WineManager(tmp_path / "no-existe", runner=FakeRunner()).detect() is None


def test_broken_wine_raises(tmp_path):
    wine = make_executable(tmp_path / "wine")
    manager = WineManager(runner=FakeRunner(CommandResult(1, "")), which=lambda _n: str(wine))

    with pytest.raises(WineError, match="falló"):
        manager.detect()


# --- Entorno ---------------------------------------------------------------


def test_wine_environment(tmp_path):
    base = {"PATH": "/usr/bin", "WINEPREFIX": "/home/u/.wine", "WINEARCH": "win32", "LANG": "es"}
    env = wine_environment(tmp_path / "pfx", base=base, extra={"LANG": "es_ES.UTF-8"})

    assert env["WINEPREFIX"] == str(tmp_path / "pfx")  # el del usuario se descarta
    assert "WINEARCH" not in env
    assert env["WINEDEBUG"] == "-all"
    assert env["WINEDLLOVERRIDES"] == "mscoree=;mshtml="
    assert env["PATH"] == "/usr/bin"
    assert env["LANG"] == "es_ES.UTF-8"


def test_wine_environment_with_arch(tmp_path):
    env = wine_environment(tmp_path, arch="win32", debug="err+all", dll_overrides="", base={})

    assert env["WINEARCH"] == "win32"
    assert env["WINEDEBUG"] == "err+all"
    assert "WINEDLLOVERRIDES" not in env


# --- run_command (real, con el intérprete de Python) ------------------------


def test_run_command_captures_output_and_code():
    result = run_command(
        [sys.executable, "-c", "import sys; print('hola'); sys.exit(3)"], dict(os.environ), 30
    )
    assert result == CommandResult(3, "hola\n")


def test_run_command_missing_program():
    with pytest.raises(WineError, match="No se encuentra"):
        run_command(["/no/existe/wine"], {}, 5)


def test_run_command_timeout():
    with pytest.raises(WineTimeoutError, match="no terminó"):
        run_command([sys.executable, "-c", "import time; time.sleep(5)"], dict(os.environ), 0.5)
