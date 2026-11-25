import pytest

from pokemon_to_linux.domain.compatibility import CompatibilityStatus
from pokemon_to_linux.domain.profile import ProfileError
from pokemon_to_linux.infrastructure.filesystem.profile_store import (
    MAX_PROFILE_SIZE,
    builtin_profiles_dir,
    load_profiles,
)


def toml(profile_id="mi-juego", title="Mi juego", extra=""):
    return (
        f'schema = 1\nid = "{profile_id}"\nname = "{title}"\n[match]\ntitles = ["{title}"]\n{extra}'
    )


@pytest.fixture
def dirs(tmp_path):
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    builtin.mkdir()
    user.mkdir()
    return builtin, user


def test_builtin_profiles_are_valid_and_include_pokemon_z():
    profiles = load_profiles(None)

    assert profiles.errors == ()
    pokemon_z = profiles.get("pokemon-z")
    assert pokemon_z is not None
    assert pokemon_z.match.titles == ("Pokemon Z",)
    assert pokemon_z.match.runtimes == ("mkxp-z",)
    assert pokemon_z.save_dirs == ("%USERPROFILE%/Saved Games/Pokemon Z",)
    assert pokemon_z.status is CompatibilityStatus.PARTIAL
    assert builtin_profiles_dir().is_dir()


def test_user_profiles_come_first_and_override_builtin(dirs):
    builtin, user = dirs
    (builtin / "a.toml").write_text(toml("pokemon-z", "Pokemon Z"), encoding="utf-8")
    (builtin / "b.toml").write_text(toml("otro", "Otro"), encoding="utf-8")
    (user / "mio.toml").write_text(
        toml("pokemon-z", "Pokemon Z", '[wine]\narch = "win32"\n'), encoding="utf-8"
    )
    (user / "nuevo.toml").write_text(toml("nuevo", "Nuevo"), encoding="utf-8")
    (user / "notas.txt").write_text("no es un perfil", encoding="utf-8")

    profiles = load_profiles(user, builtin_dir=builtin)

    assert [p.id for p in profiles.profiles] == ["pokemon-z", "nuevo", "otro"]
    assert profiles.get("pokemon-z").arch == "win32"
    assert profiles.get("pokemon-z").source == str(user / "mio.toml")
    assert profiles.errors == ()


def test_broken_user_profiles_are_reported_not_fatal(dirs):
    builtin, user = dirs
    (user / "1-sintaxis.toml").write_text("esto = = no es toml", encoding="utf-8")
    (user / "2-campo.toml").write_text(toml(extra="peligro = 1\n"), encoding="utf-8")
    (user / "3-entorno.toml").write_text(
        toml(extra='[wine.environment]\nLD_PRELOAD = "x.so"\n'), encoding="utf-8"
    )
    (user / "4-binario.toml").write_bytes(b"\xff\xfe\x00")
    (user / "5-grande.toml").write_text("#" * (MAX_PROFILE_SIZE + 1), encoding="utf-8")
    (user / "6-bueno.toml").write_text(toml("bueno"), encoding="utf-8")
    (user / "7-repetido.toml").write_text(toml("bueno"), encoding="utf-8")

    profiles = load_profiles(user, builtin_dir=builtin)

    assert [p.id for p in profiles.profiles] == ["bueno"]
    errors = "\n".join(profiles.errors)
    assert len(profiles.errors) == 6
    for text in ("TOML no válido", "campos desconocidos", "LD_PRELOAD", "demasiado", "repetido"):
        assert text in errors


def test_missing_user_dir_is_fine(dirs, tmp_path):
    builtin, _ = dirs
    assert load_profiles(tmp_path / "no-existe", builtin_dir=builtin).profiles == ()


def test_broken_builtin_profile_is_a_bug(dirs):
    builtin, _ = dirs
    (builtin / "roto.toml").write_text("schema = 1\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="perfiles integrados/roto.toml"):
        load_profiles(None, builtin_dir=builtin)


def test_duplicate_builtin_ids_are_a_bug(dirs):
    builtin, _ = dirs
    (builtin / "a.toml").write_text(toml("x"), encoding="utf-8")
    (builtin / "b.toml").write_text(toml("x"), encoding="utf-8")

    with pytest.raises(ProfileError, match="ya lo usa"):
        load_profiles(None, builtin_dir=builtin)
