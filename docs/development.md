# Guía de desarrollo

## Requisitos

- Python **3.12 o superior**
- Git
- Bibliotecas del sistema que necesita Qt 6 (ver abajo)
- Wine, solo a partir del sprint 3

### Paquetes del sistema en Linux

**Debian / Ubuntu** (comprobado en Ubuntu 24.04):

```bash
sudo apt install python3 python3-venv python3-pip \
  libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xkb1
```

**Fedora** (sin probar):

```bash
sudo dnf install python3 libxkbcommon-x11 xcb-util-cursor xcb-util-wm \
  xcb-util-image xcb-util-keysyms xcb-util-renderutil
```

**Arch / Manjaro** (sin probar):

```bash
sudo pacman -S python libxkbcommon-x11 xcb-util-cursor xcb-util-wm \
  xcb-util-image xcb-util-keysyms xcb-util-renderutil
```

Las instalaciones de escritorio suelen traer casi todas estas bibliotecas. La que más falta es `libxcb-cursor0` (`xcb-util-cursor`), obligatoria en X11 desde Qt 6.5. Si falta alguna, la ventana no abre y aparece este error:

```
qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.
```

Para ver qué bibliotecas faltan exactamente:

```bash
ldd .venv/lib/python3*/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so | grep "not found"
```

> Debian 12 trae Python 3.11, que no es suficiente. Usa Debian 13, Ubuntu 24.04 o una versión más reciente, o instala Python 3.12 por otra vía (p. ej. `uv python install 3.12`).

### Wine (desde el sprint 3)

Pokémon Z y la mayoría de fangames de RPG Maker XP son **de 32 bits**, así que Wine necesita soporte de 32 bits.

| Distribución | Comando |
|---|---|
| Debian / Ubuntu | `sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install wine wine64 wine32:i386` |
| Fedora | `sudo dnf install wine` (trae el soporte de 32 bits) |
| Arch / Manjaro | activar `[multilib]` en `/etc/pacman.conf` y `sudo pacman -S wine` |

Comprueba que funciona:

```bash
pokemon-to-linux-cli wine --probe
#   64 bits:     sí
#   32 bits:     sí      ← imprescindible para Pokémon Z
```

En Ubuntu, el paquete `wine64` solo no basta. No añade `wine` al PATH (se queda en `/usr/lib/wine/wine64`; la aplicación lo encuentra igualmente) y **no ejecuta programas de 32 bits**: falta `wine32:i386`.

## Puesta en marcha

```bash
git clone https://github.com/josebullii/Port-Community-Pokemon-to-Linux.git
cd Port-Community-Pokemon-to-Linux
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pokemon-to-linux                   # o: python -m pokemon_to_linux
```

## Pruebas y calidad

```bash
pytest                    # todas las pruebas
pytest tests/unit         # solo las unitarias (rápidas, no necesitan Qt)
pytest -m integration     # solo las de integración (Qt sin pantalla)
pytest -m wine            # solo las que usan Wine real (se omiten si no está)
ruff check .              # lint
ruff format .             # formato
```

Las pruebas de Qt usan `QT_QPA_PLATFORM=offscreen`, que se fija en `tests/conftest.py`, así que funcionan sin pantalla.

### Fixtures disponibles (`tests/conftest.py`)

| Fixture | Qué hace |
|---|---|
| `qapp` | `QApplication` compartida por toda la sesión |
| `xdg_tmp` | Redirige las cuatro rutas XDG a un directorio temporal |
| `_reset_app_logger` | (automática) Cierra los handlers del log tras cada prueba |
| `make_pe` | Construye un ejecutable PE mínimo y válido (arquitectura, DLL importadas, marcadores) |
| `make_game` | Crea una carpeta de juego RPG Maker XP falsa y configurable (INI, exe, DLL, `Data/`…). Con `exe="runnable"`, `Game.exe` es un programa real de 32 bits que termina con código 7 |

### Archivos de juegos en las pruebas

Los archivos reales de juegos **nunca** se suben al repositorio. Las pruebas generan juegos falsos al vuelo con `make_game` y `make_pe`, así que no hace falta ningún binario. Para pruebas manuales con juegos reales, guárdalos en `games/` (está en `.gitignore`) o fuera del repositorio.

### Pruebas con juegos reales

Son opcionales y en el CI se omiten. Se activan indicando la ruta de tu copia:

```bash
PTL_POKEMON_Z_PATH="/ruta/a/POKEMON Z V2.19" pytest -m realgame
```

## Analizar un juego desde la terminal

```bash
pokemon-to-linux-cli analyze "/ruta/a/POKEMON Z V2.19"          # informe legible
pokemon-to-linux-cli analyze "/ruta/a/POKEMON Z V2.19" --json   # JSON
```

Códigos de salida: `0` motor detectado, `1` no detectado, `2` ruta no válida.

## Lanzar un juego con Wine desde la terminal

```bash
pokemon-to-linux-cli wine                    # qué Wine hay instalado
pokemon-to-linux-cli wine --probe            # ¿ejecuta 32 y 64 bits?
pokemon-to-linux-cli run "/ruta/al/juego"    # prepara el prefijo y lanza el juego
pokemon-to-linux-cli run "/ruta/al/juego" --arch win32 --id mi-juego --timeout 60
```

`run` devuelve el código de salida del juego. Si no terminó normalmente devuelve `1`, y si no se pudo lanzar, `2`.

Ctrl+C:
- **Con el juego en marcha**, lo detiene de forma ordenada (`wineserver -k`).
- **Mientras se prepara el prefijo**, cancela, borra el prefijo a medias y devuelve `130`.

- **Prefijos**: `~/.local/share/pokemon-to-linux/prefixes/<id>`.
- **Log de cada lanzamiento**: `~/.local/state/pokemon-to-linux/logs/games/<id>/<fecha>.log`. Se conservan los últimos 20 por juego.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push y en cada pull request.

**Job principal** (Ubuntu 24.04, Python 3.12 y 3.13):

1. Ruff (lint y formato)
2. pytest
3. Arranque real de la aplicación durante 5 s sin pantalla, comprobando el log
4. CLI, bibliotecas X11 completas y arranque en X11 (Xvfb)
5. Construcción del paquete (wheel)

**Job `wine`** (Ubuntu 24.04, Python 3.12):

1. Instala Wine 9.0 con `wine32:i386`.
2. Comprueba con `wine --probe` que ejecuta 32 y 64 bits.
3. Ejecuta `pytest -m wine`, que incluye lanzar el juego de prueba de extremo a extremo.

## Convenciones

- Código, nombres y docstrings técnicos en inglés o español, pero de forma coherente dentro de cada módulo. Los textos de la interfaz y la documentación, en español.
- Logs: `get_logger(__name__)` en cada módulo.
- Procesos: listas de argumentos, nunca `shell=True` (Ruff lo comprueba con las reglas `S`).
- Cada sprint en su rama (`sprint1`, `sprint2`, …), que se fusiona en `master` al terminarlo.
