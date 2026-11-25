from pokemon_to_linux.application.diagnose_output import (
    GENERIC_ISSUES,
    MAX_LINE,
    OutputDiagnoser,
)
from pokemon_to_linux.domain.profile import GameProfile, KnownIssue, ProfileMatch

# Salida real de Pokémon Z en Ubuntu 24.04 sin OpenGL de 32 bits.
NO_GL32_OUTPUT = [
    "RGSS version 1 (RPG Maker XP) ",
    "Error creating window: No matching GL pixel format available ",
]

# Salida real de Pokémon Z funcionando.
OK_OUTPUT = [
    "RGSS version 1 (RPG Maker XP) ",
    "ALC_SOFT_pause_device present ",
    "GL Vendor    : Mesa ",
    "GL Renderer  : llvmpipe (LLVM 20.1.2, 256 bits) ",
    "GL Version   : 4.5 (Core Profile) Mesa 25.2.8-0ubuntu0.24.04.5 ",
    "GLSL Version : 4.50 ",
]


def test_missing_32_bit_opengl_is_recognized():
    diagnoser = OutputDiagnoser()
    diagnoser.feed_all(NO_GL32_OUTPUT)

    [finding] = diagnoser.findings
    assert finding.issue.id == "opengl-sin-formato"
    assert "libgl1:i386" in finding.issue.solution
    assert finding.line == "Error creating window: No matching GL pixel format available"
    assert finding.to_dict()["id"] == "opengl-sin-formato"


# Salida real con WINEDEBUG=fixme-all (sprint 4): Wine dice la causa exacta.
NO_GL32_WINE_OUTPUT = [
    "RGSS version 1 (RPG Maker XP) ",
    "0024:err:wgl:init_opengl Failed to load libGL: libGL.so.1: cannot open shared object "
    "file: No such file or directory",
    "0024:err:wgl:init_opengl OpenGL support is disabled.",
    "0024:err:wgl:set_pixel_format Invalid format 0",
    "Error creating window: No matching GL pixel format available ",
]


def test_wine_explains_missing_libgl():
    diagnoser = OutputDiagnoser()
    diagnoser.feed_all(NO_GL32_WINE_OUTPUT)

    [finding] = diagnoser.findings
    assert finding.issue.id == "opengl-sin-formato"
    assert "libGL.so.1: cannot open shared object file" in finding.line


def test_working_game_has_no_findings():
    diagnoser = OutputDiagnoser()
    diagnoser.feed_all(OK_OUTPUT)
    assert diagnoser.findings == ()


def test_wine_messages():
    diagnoser = OutputDiagnoser()
    diagnoser.feed_all(
        [
            "it looks like wine32 is missing, you should install it.",
            '0024:err:module:import_dll Library d3dx9_43.dll (which is needed by L"C:\\\\x") '
            "not found",
            "Make sure that your X server is running and that $DISPLAY is set correctly.",
        ]
    )
    assert [f.issue.id for f in diagnoser.findings] == [
        "wine32-falta",
        "dll-no-encontrada",
        "sin-pantalla",
    ]


def test_each_issue_is_reported_once():
    diagnoser = OutputDiagnoser()

    first = diagnoser.feed(NO_GL32_OUTPUT[1])
    again = diagnoser.feed(NO_GL32_OUTPUT[1])

    assert first is not None
    assert again is None
    assert len(diagnoser.findings) == 1


def test_profile_issues_with_output_are_included():
    issue = KnownIssue("cierre", "Se cierra", "Desactiva X", output=("Stack level too deep",))
    no_output = KnownIssue("lento", "Va lento", "Quita VSync")
    profile = GameProfile(
        id="z", name="Z", match=ProfileMatch(titles=("Z",)), known_issues=(issue, no_output)
    )
    diagnoser = OutputDiagnoser(profile)

    diagnoser.feed("SystemStackError: Stack level too deep")

    assert [f.issue for f in diagnoser.findings] == [issue]


def test_long_lines_are_trimmed():
    diagnoser = OutputDiagnoser()
    diagnoser.feed("x" * (MAX_LINE + 10) + "No matching GL pixel format available")
    assert diagnoser.findings == ()
    diagnoser.feed("y" * 1000 + "No matching GL pixel format available")
    assert len(diagnoser.findings[0].line) == 300


def test_generic_issue_ids_are_unique():
    ids = [i.id for i in GENERIC_ISSUES]
    assert len(ids) == len(set(ids))
