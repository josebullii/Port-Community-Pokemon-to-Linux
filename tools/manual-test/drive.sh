#!/usr/bin/env bash
# Mando a distancia para probar un juego (o la interfaz) en una pantalla virtual.
#
# Sirve para repetir las pruebas manuales de docs/compatibility.md sin monitor:
# en WSL, por SSH o en un servidor. Necesita Xvfb, xdotool, x11-apps (xwd) e
# ImageMagick (convert):
#
#   sudo apt install xvfb xdotool x11-apps imagemagick
#
# Uso:
#   drive.sh start            Xvfb y el juego con «pokemon-to-linux-cli run»
#   drive.sh gui              Xvfb y la interfaz gráfica (pokemon-to-linux)
#   drive.sh keys K1 K2 ...   pulsa teclas (cada una 120 ms); «w:N» espera N s
#   drive.sh hold K SEG       mantiene pulsada una tecla
#   drive.sh type TEXTO       escribe un texto (p. ej. una ruta en un diálogo)
#   drive.sh click X Y        clic en la pantalla
#   drive.sh shot NOMBRE      captura de la ventana del juego
#   drive.sh screen NOMBRE    captura de toda la pantalla
#   drive.sh status | stop
#
# Variables:
#   PTL_GAME     carpeta del juego (obligatoria para «start»)
#   PTL_WINDOW   título de la ventana del juego (por defecto «Pokemon Z»)
#   PTL_OUT      carpeta de las capturas y la salida (por defecto ./capturas)
#   PTL_DISPLAY  pantalla virtual (por defecto :95)
#   PTL_SIZE     tamaño de la pantalla (por defecto 1280x800x24)
#
# Ejemplo (Pokémon Z: título, «Continuar» y una captura):
#   PTL_GAME=~/Juegos/"POKEMON Z V2.19" drive.sh start
#   drive.sh keys w:5 Return w:3 Return w:5 && drive.sh shot continuar
#   drive.sh stop
set -u

OUT=${PTL_OUT:-$PWD/capturas}
WINDOW=${PTL_WINDOW:-Pokemon Z}
export DISPLAY=${PTL_DISPLAY:-:95}
SIZE=${PTL_SIZE:-1280x800x24}
mkdir -p "$OUT"

win() { xdotool search --name "^${WINDOW}\$" 2>/dev/null | head -1; }

start_xvfb() {
    pgrep -f "Xvfb ${DISPLAY}( |\$)" >/dev/null && return
    setsid nohup Xvfb "$DISPLAY" -screen 0 "$SIZE" >/dev/null 2>&1 &
    # No basta con mirar /tmp/.X11-unix: en WSL Xvfb solo usa un socket abstracto.
    for _ in $(seq 1 20); do
        xdotool getdisplaygeometry >/dev/null 2>&1 && return
        sleep 0.25
    done
    echo "Xvfb no ha arrancado en $DISPLAY" >&2
    exit 1
}

case "${1:-}" in
start)
    : "${PTL_GAME:?indica la carpeta del juego en PTL_GAME}"
    start_xvfb
    setsid nohup pokemon-to-linux-cli run "$PTL_GAME" >"$OUT/run.txt" 2>&1 </dev/null &
    for i in $(seq 1 180); do
        sleep 1
        [ -n "$(win)" ] && break
    done
    echo "ventana: $(win) tras ${i} s (salida en $OUT/run.txt)"
    ;;
gui)
    start_xvfb
    # Qt preferiría Wayland si existe (p. ej. WSLg) y la ventana no saldría en Xvfb.
    QT_QPA_PLATFORM=xcb setsid nohup pokemon-to-linux >"$OUT/gui.txt" 2>&1 </dev/null &
    sleep 4
    echo "interfaz lanzada (salida en $OUT/gui.txt)"
    ;;
keys)
    shift
    W=$(win)
    [ -n "$W" ] && xdotool windowfocus "$W" 2>/dev/null
    for k in "$@"; do
        case "$k" in
        w:*) sleep "${k#w:}" ;;
        *)
            xdotool keydown "$k"
            sleep 0.12
            xdotool keyup "$k"
            sleep 0.35
            ;;
        esac
    done
    ;;
hold)
    W=$(win)
    [ -n "$W" ] && xdotool windowfocus "$W" 2>/dev/null
    xdotool keydown "$2"
    sleep "$3"
    xdotool keyup "$2"
    ;;
type)
    xdotool type --delay 30 "$2"
    ;;
click)
    xdotool mousemove "$2" "$3" click 1
    ;;
shot)
    W=$(win)
    [ -z "$W" ] && { echo "no hay ventana «$WINDOW»" >&2; exit 1; }
    xwd -id "$W" -silent | convert xwd:- "$OUT/$2.png" && echo "$OUT/$2.png"
    ;;
screen)
    xwd -root -silent | convert xwd:- "$OUT/$2.png" && echo "$OUT/$2.png"
    ;;
status)
    echo "ventana: $(win)"
    ps -eo etimes,pcpu,rss,comm | grep -i -E "game.exe|wineserver|pokemon-to-linux" || true
    tail -3 "$OUT/run.txt" 2>/dev/null || true
    ;;
stop)
    pkill -INT -f "pokemon-to-linux-cli run" || true
    pkill -f "bin/pokemon-to-linux( |\$)" || true
    sleep 8
    tail -5 "$OUT/run.txt" 2>/dev/null || true
    pkill -f "Xvfb ${DISPLAY}( |\$)" || true
    ;;
*)
    sed -n '2,32p' "$0"
    exit 2
    ;;
esac
