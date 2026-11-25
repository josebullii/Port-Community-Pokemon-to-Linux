import copy

import pytest

from pokemon_to_linux.domain.compatibility import CompatibilityStatus
from pokemon_to_linux.domain.profile import (
    GameProfile,
    ProfileError,
    ProfileMatch,
    check_folder,
    parse_profile,
    select_profile,
)

FULL = {
    "schema": 1,
    "id": "mi-juego",
    "name": "Mi juego",
    "description": "Un fangame de prueba",
    "match": {
        "engine": "rpgmaker_xp",
        "runtimes": ["mkxp-z"],
        "titles": ["Mi Juego"],
        "files": ["mkxp.json"],
    },
    "wine": {"arch": "win64", "environment": {"LANG": "es_ES.UTF-8", "SDL_AUDIODRIVER": "pulse"}},
    "saves": {"paths": ["%USERPROFILE%/Saved Games/Mi Juego"], "config": ["%appdata%\\Mi Juego"]},
    "known_issues": [
        {"id": "rapido", "symptom": "Va rápido", "solution": "Quita VSync"},
        {
            "id": "gl",
            "symptom": "No abre",
            "solution": "Instala OpenGL",
            "output": ["No matching GL pixel format"],
        },
    ],
    "compatibility": {"status": "partial", "notes": "Probado hasta el título"},
}


def data(**changes):
    result = copy.deepcopy(FULL)
    for dotted, value in changes.items():
        *path, key = dotted.split("__")
        target = result
        for part in path:
            target = target[part]
        if value is ...:
            del target[key]
        else:
            target[key] = value
    return result


def test_full_profile():
    profile = parse_profile(FULL, "mi-juego.toml")

    assert profile.id == "mi-juego"
    assert profile.name == "Mi juego"
    assert profile.match.runtimes == ("mkxp-z",)
    assert profile.match.specificity == 4
    assert profile.arch == "win64"
    assert profile.environment == {"LANG": "es_ES.UTF-8", "SDL_AUDIODRIVER": "pulse"}
    assert profile.save_dirs == ("%USERPROFILE%/Saved Games/Mi Juego",)
    assert profile.config_dirs == ("%APPDATA%/Mi Juego",)  # normalizada
    assert [i.id for i in profile.known_issues] == ["rapido", "gl"]
    assert profile.known_issues[1].found_in("Error: No matching GL pixel format available")
    assert not profile.known_issues[0].found_in("cualquier cosa")
    assert profile.status is CompatibilityStatus.PARTIAL
    assert profile.status.label == "Parcial"
    assert profile.source == "mi-juego.toml"


def test_minimal_profile_has_defaults():
    profile = parse_profile(
        {"schema": 1, "id": "x", "name": "X", "match": {"titles": ["X"]}}, "x.toml"
    )

    assert profile.arch is None
    assert profile.environment == {}
    assert profile.save_dirs == ()
    assert profile.known_issues == ()
    assert profile.status is CompatibilityStatus.NOT_TESTED


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema": 2}, "esquema"),
        ({"schema": ...}, "obligatorio 'schema'"),
        ({"schema": True}, "tipo no válido"),
        ({"id": "Mi Juego"}, "identificador no válido"),
        ({"id": "../fuera"}, "identificador no válido"),
        ({"name": "  "}, "vacío"),
        ({"extra": 1}, "campos desconocidos: extra"),
        ({"match__engine_id": "x"}, "match: campos desconocidos"),
        ({"match": {}}, "al menos una condición"),
        ({"match__titles": "Mi Juego"}, "tipo no válido"),
        ({"match__titles": [""]}, "lista de textos"),
        ({"match__files": ["../Game.exe"]}, "ruta relativa"),
        ({"match__files": ["C:/Game.exe"]}, "ruta relativa"),
        ({"wine__arch": "win16"}, "win32 o win64"),
        ({"wine__environment": {"LD_PRELOAD": "/var/x.so"}}, "no permitida: LD_PRELOAD"),
        ({"wine__environment": {"PATH": "/opt"}}, "no permitida: PATH"),
        ({"wine__environment": {"WINEPREFIX": "/opt"}}, "no permitida: WINEPREFIX"),
        ({"wine__environment": {"LANG": 1}}, "texto corto"),
        ({"wine__environment": {"LANG": "x" * 300}}, "texto corto"),
        ({"wine__environment": "LANG=es"}, "debe ser una tabla"),
        ({"saves__paths": ["/home/yo/partidas"]}, "debe empezar por"),
        ({"saves__paths": ["%USERPROFILE%/../../etc"]}, "no puede salir"),
        ({"saves__paths": ["%TEMP%/x"]}, "debe empezar por"),
        ({"known_issues": [{"id": "a", "symptom": "s"}]}, "obligatorio 'solution'"),
        (
            {"known_issues": [{"id": "a", "symptom": "s", "solution": "x"}] * 2},
            "repetidos",
        ),
        ({"known_issues": ["texto"]}, "debe ser una tabla"),
        ({"compatibility__status": "perfecto"}, "usa uno de"),
        ({"match": "rpgmaker_xp"}, "debe ser una tabla"),
    ],
)
def test_invalid_profiles_are_rejected(changes, message):
    with pytest.raises(ProfileError, match=message) as exc:
        parse_profile(data(**changes), "malo.toml")
    assert str(exc.value).startswith("malo.toml")


def test_check_folder_normalizes_separators_and_case():
    assert check_folder("%localappdata%\\Juego\\Saves", "x") == "%LOCALAPPDATA%/Juego/Saves"
    assert check_folder("%GAMEDIR%", "x") == "%GAMEDIR%"


# --- Selección -----------------------------------------------------------------


def make(profile_id, **match):
    return GameProfile(id=profile_id, name=profile_id, match=ProfileMatch(**match))


GAME = {"engine": "rpgmaker_xp", "runtime": "mkxp-z", "title": "Pokemon Z"}


def has(*files):
    wanted = {f.lower() for f in files}
    return lambda f: f.lower() in wanted


def test_match_conditions():
    m = ProfileMatch(engine="rpgmaker_xp", runtimes=("mkxp-z",), titles=("pokemon z",))
    assert m.matches(**GAME, has_file=has())
    assert m.matches(**{**GAME, "title": "  POKEMON Z "}, has_file=has())
    assert not m.matches(**{**GAME, "title": None}, has_file=has())
    assert not m.matches(**{**GAME, "runtime": "rgss1"}, has_file=has())
    assert not m.matches(**{**GAME, "engine": "rpgmaker_vx"}, has_file=has())
    assert not ProfileMatch(files=("mkxp.json",)).matches(**GAME, has_file=has())
    assert ProfileMatch(files=("mkxp.json",)).matches(**GAME, has_file=has("mkxp.json"))


def test_most_specific_profile_wins():
    generic = make("generico", engine="rpgmaker_xp")
    specific = make("pokemon-z", engine="rpgmaker_xp", titles=("Pokemon Z",))
    other = make("otro", titles=("Otro juego",))

    chosen = select_profile([generic, specific, other], **GAME, has_file=has())

    assert chosen is specific


def test_first_profile_wins_a_tie_and_none_if_nothing_matches():
    a = make("a", titles=("Pokemon Z",))
    b = make("b", titles=("Pokemon Z",))

    assert select_profile([a, b], **GAME, has_file=has()) is a
    assert select_profile([make("c", titles=("Otro",))], **GAME, has_file=has()) is None
