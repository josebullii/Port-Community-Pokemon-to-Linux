from pathlib import Path

import pytest

from pokemon_to_linux.infrastructure.wine.prefix_manager import (
    TEST_EXIT_CODE,
    Prefix,
    PrefixError,
    PrefixManager,
    read_prefix_arch,
    resolve_arch,
    slugify,
    validate_game_id,
)
from pokemon_to_linux.infrastructure.wine.wine_manager import (
    CommandResult,
    WineInstallation,
    WineTimeoutError,
)

WINE = WineInstallation(
    wine=Path("/usr/bin/wine"),
    wineserver=Path("/usr/bin/wineserver"),
    version="9.0",
    flavor=None,
    description="wine-9.0",
)


class FakeWine:
    """Simula wine/wineserver: wineboot crea system.reg con la arquitectura pedida."""

    def __init__(self, *, wineboot_code=0, created_arch=None, program_code=TEST_EXIT_CODE):
        self.calls = []
        self.wineboot_code = wineboot_code
        self.created_arch = created_arch
        self.program_code = program_code

    def __call__(self, args, env, timeout, cwd):
        self.calls.append((list(args), dict(env)))
        prefix = Path(env["WINEPREFIX"])
        if args[1:] == ["wineboot", "--init"]:
            if self.wineboot_code == 0:
                prefix.mkdir(parents=True, exist_ok=True)
                arch = self.created_arch or env.get("WINEARCH", "win64")
                (prefix / "system.reg").write_text(
                    "WINE REGISTRY Version 2\n;; All keys relative to \\\\Machine\n\n"
                    f"#arch={arch}\n"
                )
            return CommandResult(self.wineboot_code, "err:wineboot: algo falló\n")
        if args[0].endswith(".exe") or (len(args) > 1 and args[1].endswith(".exe")):
            return CommandResult(self.program_code, "")
        return CommandResult(0, "")

    def commands(self):
        return [args[1:] if "wineserver" not in args[0] else ["wineserver", *args[1:]]
                for args, _ in self.calls]  # fmt: skip


@pytest.fixture
def prefixes(tmp_path):
    return tmp_path / "prefixes"


def manager(prefixes, fake, **kw):
    return PrefixManager(prefixes, WINE, runner=fake, registry_wait=0.5, **kw)


# --- Utilidades -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Pokémon Z v2.19", "pokemon-z-v2.19"),
        ("POKEMON Z V2.19", "pokemon-z-v2.19"),
        ("  ¡Añil!  ", "anil"),
        ("../../etc", "etc"),
        ("ポケモン", "juego"),
        ("x" * 100, "x" * 64),
    ],
)
def test_slugify(name, slug):
    assert slugify(name) == slug
    validate_game_id(slug)  # siempre produce un id válido


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "A", "-x", "a..b", "x" * 65, "a b"])
def test_invalid_game_ids(bad):
    with pytest.raises(PrefixError, match="no válido"):
        validate_game_id(bad)


@pytest.mark.parametrize(
    ("bits", "requested", "expected"),
    [(32, None, "win64"), (64, None, "win64"), (None, None, "win64"), (32, "win32", "win32")],
)
def test_resolve_arch(bits, requested, expected):
    assert resolve_arch(bits, requested) == expected


def test_resolve_arch_rejects_win32_for_64_bit():
    with pytest.raises(PrefixError, match="64 bits"):
        resolve_arch(64, "win32")


def test_resolve_arch_rejects_unknown():
    with pytest.raises(PrefixError, match="no válida"):
        resolve_arch(32, "win16")


def test_read_prefix_arch(tmp_path):
    assert read_prefix_arch(tmp_path) is None
    (tmp_path / "system.reg").write_text("WINE REGISTRY Version 2\n\n#arch=win32\n")
    assert read_prefix_arch(tmp_path) == "win32"


# --- Creación ---------------------------------------------------------------


def test_create_runs_wineboot_then_waits_for_wineserver(prefixes):
    fake = FakeWine()
    prefix = manager(prefixes, fake).create("pokemon-z")

    assert prefix == Prefix("pokemon-z", prefixes / "pokemon-z", "win64")
    assert fake.commands() == [["wineboot", "--init"], ["wineserver", "-w"]]
    env = fake.calls[0][1]
    assert env["WINEPREFIX"] == str(prefixes / "pokemon-z")
    assert env["WINEARCH"] == "win64"
    assert env["WINEDLLOVERRIDES"] == "mscoree=;mshtml="


def test_create_win32(prefixes):
    prefix = manager(prefixes, FakeWine()).create("juego", "win32")
    assert prefix.arch == "win32"


def test_create_fails_and_cleans_up_when_wineboot_fails(prefixes):
    with pytest.raises(PrefixError, match="wineboot falló.*algo falló"):
        manager(prefixes, FakeWine(wineboot_code=1)).create("juego")
    assert not (prefixes / "juego").exists()


def test_create_fails_when_wine_ignores_win32(prefixes):
    """Wine solo-WoW64: se pide win32 pero se crea win64."""
    with pytest.raises(PrefixError, match="win64 en vez de win32"):
        manager(prefixes, FakeWine(created_arch="win64")).create("juego", "win32")
    assert not (prefixes / "juego").exists()


def test_create_cleans_up_on_timeout(prefixes):
    def slow(args, env, timeout, cwd):
        Path(env["WINEPREFIX"]).mkdir(parents=True)
        raise WineTimeoutError("wine no terminó en 300 s")

    with pytest.raises(WineTimeoutError):
        manager(prefixes, slow).create("juego")
    assert not (prefixes / "juego").exists()


def test_create_refuses_to_overwrite(prefixes):
    (prefixes / "juego").mkdir(parents=True)
    (prefixes / "juego" / "algo.txt").write_text("datos del usuario")

    with pytest.raises(PrefixError, match="no se sobrescribe"):
        manager(prefixes, FakeWine()).create("juego")
    assert (prefixes / "juego" / "algo.txt").exists()


def test_ensure_reuses_existing(prefixes):
    fake = FakeWine()
    pm = manager(prefixes, fake)
    first = pm.ensure("juego")
    calls = len(fake.calls)

    assert pm.ensure("juego") == first
    assert len(fake.calls) == calls  # no vuelve a ejecutar wineboot


def test_ensure_refuses_arch_change(prefixes):
    pm = manager(prefixes, FakeWine())
    pm.ensure("juego", "win32")

    with pytest.raises(PrefixError, match="ya existe como win32"):
        pm.ensure("juego", "win64")


# --- Mantenimiento ------------------------------------------------------------


def test_delete_kills_processes_and_removes(prefixes):
    fake = FakeWine()
    pm = manager(prefixes, fake)
    pm.create("juego")

    assert pm.delete("juego") is True
    assert ["wineserver", "-k"] in fake.commands()
    assert not (prefixes / "juego").exists()
    assert pm.delete("juego") is False


def test_delete_never_follows_symlinks(prefixes, tmp_path):
    import os

    victim = tmp_path / "importante"
    victim.mkdir()
    prefixes.mkdir()
    try:
        os.symlink(victim, prefixes / "juego", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("este sistema no permite crear enlaces simbólicos")

    with pytest.raises(PrefixError, match="sospechosa"):
        manager(prefixes, FakeWine()).delete("juego")
    assert victim.exists()


def test_kill_without_wineserver_does_not_crash(prefixes):
    wine = WineInstallation(Path("/usr/bin/wine"), None, "9.0", None, "wine-9.0")
    fake = FakeWine()
    pm = PrefixManager(prefixes, wine, runner=fake, registry_wait=0.2)
    pm.kill(Prefix("juego", prefixes / "juego", "win64"))

    assert fake.calls == []


# --- Programa de prueba ---------------------------------------------------------


@pytest.mark.parametrize(("code", "ok"), [(TEST_EXIT_CODE, True), (1, False)])
def test_run_test_program(prefixes, code, ok):
    fake = FakeWine(program_code=code)
    pm = manager(prefixes, fake)
    prefix = pm.create("juego")

    result = pm.run_test_program(prefix, 32)

    assert result.ok is ok
    assert result.exit_code == code
    exe = prefix.path / "drive_c" / "pokemon-to-linux" / "prueba_32.exe"
    assert exe.read_bytes()[:2] == b"MZ"


def test_run_test_program_timeout_is_a_failed_result(prefixes):
    pm = manager(prefixes, FakeWine())
    prefix = pm.create("juego")

    def hang(*_args):
        raise WineTimeoutError("no terminó")

    pm._run = hang
    result = pm.run_test_program(prefix, 64)

    assert result.ok is False
    assert result.exit_code is None


# --- Interrupciones durante la creación ------------------------------------------


def test_ctrl_c_during_wineboot_removes_partial_prefix(prefixes):
    """Regresión: un Ctrl+C dejaba un prefijo sin system.reg que bloqueaba los reintentos."""
    calls = []

    def interrupted(args, env, timeout, cwd):
        calls.append(list(args[1:]))
        if args[1:] == ["wineboot", "--init"]:
            (Path(env["WINEPREFIX"]) / "drive_c").mkdir(parents=True)
            raise KeyboardInterrupt
        return CommandResult(0, "")

    pm = manager(prefixes, interrupted)
    with pytest.raises(KeyboardInterrupt):
        pm.create("juego")

    assert not (prefixes / "juego").exists()
    assert ["-k"] in calls  # se cierran los procesos que quedaran

    # El siguiente intento funciona en vez de fallar con "no se sobrescribe".
    assert manager(prefixes, FakeWine()).ensure("juego").arch == "win64"


def test_cleanup_still_removes_prefix_if_wineserver_fails(prefixes):
    def broken(args, env, timeout, cwd):
        if args[1:] == ["wineboot", "--init"]:
            Path(env["WINEPREFIX"]).mkdir(parents=True)
            return CommandResult(1, "fallo")
        raise WineTimeoutError("wineserver colgado")

    with pytest.raises(PrefixError, match="wineboot falló"):
        manager(prefixes, broken).create("juego")
    assert not (prefixes / "juego").exists()
