from pathlib import Path

from pokemon_to_linux import APP_ID
from pokemon_to_linux.config import AppPaths

HOME = Path("/home/tester").absolute()


def test_defaults_use_home_when_xdg_unset():
    paths = AppPaths.from_environment(env={}, home=HOME)

    assert paths.data_dir == HOME / ".local/share" / APP_ID
    assert paths.config_dir == HOME / ".config" / APP_ID
    assert paths.cache_dir == HOME / ".cache" / APP_ID
    assert paths.state_dir == HOME / ".local/state" / APP_ID


def test_xdg_variables_override_defaults(tmp_path):
    env = {
        "XDG_DATA_HOME": str(tmp_path / "d"),
        "XDG_CONFIG_HOME": str(tmp_path / "c"),
        "XDG_CACHE_HOME": str(tmp_path / "k"),
        "XDG_STATE_HOME": str(tmp_path / "s"),
    }
    paths = AppPaths.from_environment(env=env, home=HOME)

    assert paths.data_dir == tmp_path / "d" / APP_ID
    assert paths.config_dir == tmp_path / "c" / APP_ID
    assert paths.cache_dir == tmp_path / "k" / APP_ID
    assert paths.state_dir == tmp_path / "s" / APP_ID


def test_relative_or_empty_xdg_values_are_ignored():
    env = {"XDG_DATA_HOME": "relativo/datos", "XDG_CONFIG_HOME": "   "}
    paths = AppPaths.from_environment(env=env, home=HOME)

    assert paths.data_dir == HOME / ".local/share" / APP_ID
    assert paths.config_dir == HOME / ".config" / APP_ID


def test_derived_paths():
    paths = AppPaths.from_environment(env={}, home=HOME)

    assert paths.prefixes_dir == paths.data_dir / "prefixes"
    assert paths.database_path == paths.data_dir / "library.sqlite3"
    assert paths.log_dir == paths.state_dir / "logs"


def test_ensure_creates_all_directories(tmp_path):
    paths = AppPaths.from_environment(env={}, home=tmp_path)
    paths.ensure()
    paths.ensure()  # idempotente

    for directory in (
        paths.data_dir,
        paths.config_dir,
        paths.cache_dir,
        paths.state_dir,
        paths.prefixes_dir,
        paths.log_dir,
    ):
        assert directory.is_dir()
