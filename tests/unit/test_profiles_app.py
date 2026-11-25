from pathlib import Path

import pytest

from pokemon_to_linux.application.analyze_game import analyze_game
from pokemon_to_linux.application.profiles import match_profile, resolve_folder, wine_user_dir
from pokemon_to_linux.domain.profile import GameProfile, ProfileError, ProfileMatch
from pokemon_to_linux.infrastructure.filesystem.profile_store import load_profiles


@pytest.fixture
def prefix(tmp_path):
    users = tmp_path / "prefijo" / "drive_c" / "users"
    (users / "Public").mkdir(parents=True)
    (users / "jose").mkdir()
    return tmp_path / "prefijo"


def test_wine_user_dir(prefix):
    users = prefix / "drive_c" / "users"
    assert wine_user_dir(prefix, "jose") == users / "jose"
    # Si el usuario no coincide pero solo hay uno (además de Public), es ese.
    assert wine_user_dir(prefix, "otro") == users / "jose"
    (users / "ana").mkdir()
    assert wine_user_dir(prefix, "otro") == users / "otro"
    # Prefijo todavía sin crear.
    assert wine_user_dir(Path("/no/existe"), "x") == Path("/no/existe/drive_c/users/x")


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("%USERPROFILE%/Saved Games/Pokemon Z", ("jose", "Saved Games", "Pokemon Z")),
        (r"%APPDATA%\Pokemon Z", ("jose", "AppData", "Roaming", "Pokemon Z")),
        ("%LOCALAPPDATA%/X", ("jose", "AppData", "Local", "X")),
    ],
)
def test_resolve_folder_in_prefix(prefix, folder, expected):
    path = resolve_folder(folder, prefix_path=prefix, game_dir=Path("/juego"), user="jose")
    assert path == prefix.joinpath("drive_c", "users", *expected)


def test_resolve_folder_in_game_and_invalid(prefix, tmp_path):
    game = tmp_path / "juego"
    assert resolve_folder("%GAMEDIR%/Saves", prefix_path=prefix, game_dir=game) == game / "Saves"
    with pytest.raises(ProfileError):
        resolve_folder("%USERPROFILE%/../..", prefix_path=prefix, game_dir=game)


def test_pokemon_z_profile_matches_mkxp_z_game_titled_pokemon_z(make_game):
    from conftest import build_game_ini

    profiles = load_profiles(None).profiles
    pokemon_z = make_game(exe="mkxp-z", ini=build_game_ini(title="Pokemon Z"))
    other_title = make_game(exe="mkxp-z", ini=build_game_ini(title="Pokemon Nova"))
    classic = make_game(exe="rgss", ini=build_game_ini(title="Pokemon Z"))

    assert match_profile(analyze_game(pokemon_z), profiles).id == "pokemon-z"
    assert match_profile(analyze_game(other_title), profiles) is None
    assert match_profile(analyze_game(classic), profiles) is None


def test_undetected_game_has_no_profile(tmp_path):
    p = GameProfile(id="x", name="X", match=ProfileMatch(files=("algo.txt",)))
    (tmp_path / "algo.txt").write_text("")
    assert match_profile(analyze_game(tmp_path), [p]) is None


def test_profile_file_conditions_use_game_files(make_game):
    p = GameProfile(id="x", name="X", match=ProfileMatch(files=("Data/extra.dat",)))
    with_file = make_game(extra={"Data/EXTRA.dat": b""})

    assert match_profile(analyze_game(with_file), [p]) is p
    assert match_profile(analyze_game(make_game()), [p]) is None
