#!/usr/bin/env bash
# Instala Pokémon to Linux para el usuario actual (sin sudo):
#
#   ./install.sh               copia el ejecutable a ~/.local/bin y lo añade al menú
#   ./install.sh --uninstall   lo quita (no borra la biblioteca, los prefijos ni las partidas)
#
# Busca el ejecutable «pokemon-to-linux-*-x86_64» en la misma carpeta que este script.
set -euo pipefail

BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
TARGET="$BIN_DIR/pokemon-to-linux"
DESKTOP="$APPS_DIR/pokemon-to-linux.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$TARGET" "$DESKTOP"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" || true
    echo "Desinstalado. Tus datos siguen en ~/.local/share/pokemon-to-linux (biblioteca, prefijos y partidas)."
    exit 0
fi

here=$(cd "$(dirname "$0")" && pwd)
src=$(find "$here" -maxdepth 1 -type f -name 'pokemon-to-linux-*-x86_64' | sort | tail -1)
if [ -z "$src" ]; then
    echo "No encuentro el ejecutable pokemon-to-linux-*-x86_64 junto a este script." >&2
    exit 1
fi

mkdir -p "$BIN_DIR" "$APPS_DIR"
install -m 755 "$src" "$TARGET"

cat >"$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Pokémon to Linux
GenericName=Lanzador de fangames
Comment=Ejecuta fangames de Pokémon para Windows (RPG Maker XP) con Wine
Exec="$TARGET"
Icon=applications-games
Terminal=false
Categories=Game;
Keywords=pokemon;fangame;rpg maker;wine;
EOF
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" || true

echo "Instalado en $TARGET"
echo "Ábrelo desde el menú de aplicaciones («Pokémon to Linux») o con: pokemon-to-linux"
case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) echo "Aviso: $BIN_DIR aún no está en tu PATH (en Ubuntu se añade al volver a iniciar sesión)." ;;
esac
