"""La documentación no debe contradecir a los perfiles integrados."""

from pathlib import Path

from pokemon_to_linux.domain.compatibility import CompatibilityStatus
from pokemon_to_linux.infrastructure.filesystem.profile_store import load_profiles

ROOT = Path(__file__).resolve().parents[2]

ICONS = {
    "⬜": CompatibilityStatus.NOT_TESTED,
    "🟥": CompatibilityStatus.NOT_WORKING,
    "🟧": CompatibilityStatus.PARTIAL,
    "🟩": CompatibilityStatus.COMPATIBLE,
}


def wine_rows():
    """Filas de la tabla de resultados con vía Wine: {nombre del juego: estado}."""
    text = (ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 11 and cells[3] == "Wine" and cells[8] in ICONS:
            rows[cells[0]] = ICONS[cells[8]]
    return rows


def test_compatibility_matrix_matches_builtin_profiles():
    rows = wine_rows()
    for profile in load_profiles(None).profiles:
        assert profile.name in rows, f"{profile.name} no está en compatibility.md"
        assert rows[profile.name] is profile.status, (
            f"{profile.name}: compatibility.md dice {rows[profile.name].label}, "
            f"el perfil dice {profile.status.label}"
        )
