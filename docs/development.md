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

Wine (sprint 3 en adelante): `sudo apt install wine`, `sudo dnf install wine` o `sudo pacman -S wine`.

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

### Archivos de juegos en las pruebas

Los archivos reales de juegos **nunca** se suben al repositorio. Para probar el detector se crean fixtures mínimos en `tests/fixtures/`, como un `Game.ini` escrito a mano o un ejecutable PE vacío. Para pruebas manuales con juegos reales, guárdalos en `games/` (está en `.gitignore`) o fuera del repositorio.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push y en cada pull request, en **Ubuntu 24.04 con Python 3.12 y 3.13**:

1. Ruff (lint y formato)
2. pytest
3. Arranque real de la aplicación durante 5 s sin pantalla, comprobando el log
4. Construcción del paquete (wheel)

## Convenciones

- Código, nombres y docstrings técnicos en inglés o español, pero de forma coherente dentro de cada módulo. Los textos de la interfaz y la documentación, en español.
- Logs: `get_logger(__name__)` en cada módulo.
- Procesos: listas de argumentos, nunca `shell=True` (Ruff lo comprueba con las reglas `S`).
- Cada sprint en su rama (`sprint1`, `sprint2`, …), que se fusiona en `master` al terminarlo.
