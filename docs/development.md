# Guía de desarrollo

## Requisitos

- Python **3.12 o superior**
- Git
- Bibliotecas del sistema que necesita Qt 6 (ver abajo)
- Wine y OpenGL de 32 bits, a partir del sprint 3

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

Pokémon Z y la mayoría de fangames de RPG Maker XP son **de 32 bits**, así que Wine necesita soporte de 32 bits. Y como Pokémon Z (mkxp-z) dibuja con OpenGL, hace falta también **OpenGL de 32 bits**.

| Distribución | Comando |
|---|---|
| Debian / Ubuntu | `sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install wine wine64 wine32:i386 libgl1:i386 libgl1-mesa-dri:i386` |
| Fedora (sin probar) | `sudo dnf install wine mesa-libGL.i686 mesa-dri-drivers.i686` |
| Arch / Manjaro (sin probar) | activar `[multilib]` en `/etc/pacman.conf` y `sudo pacman -S wine lib32-mesa` |

Con los drivers propietarios de NVIDIA, instala también su parte de 32 bits.

Comprueba que funciona:

```bash
pokemon-to-linux-cli wine --probe
#   64 bits:     sí
#   32 bits:     sí      ← imprescindible para Pokémon Z
```

En Ubuntu, el paquete `wine64` solo no basta. No añade `wine` al PATH (se queda en `/usr/lib/wine/wine64`; la aplicación lo encuentra igualmente) y **no ejecuta programas de 32 bits**: falta `wine32:i386`.

`wine32:i386` instalado con `--no-install-recommends` no trae OpenGL de 32 bits, y Pokémon Z falla con *No matching GL pixel format available*. Para comprobar todo lo que necesita un juego:

```bash
pokemon-to-linux-cli check "/ruta/a/POKEMON Z V2.19"
#   [ok]     Sesión gráfica: X11 en :0
#   [ok]     OpenGL de 32 bits: libGL.so.1 (mesa)
#   [ok]     Carpeta del juego: ext4
#   [ok]     Wine de 32 bits: Ejecuta programas de 32 bits (prefijo pokemon-z)
#   Listo para jugar: sí
```

#### WSL

Pokémon Z funciona en WSL2 con WSLg (Ubuntu 24.04), con OpenGL por software (llvmpipe). Copia el juego al sistema de ficheros de Linux (p. ej. `~/Juegos`): desde `/mnt/c` tarda unos 2,5 minutos en mostrar el título.

Con WSLg, Qt abre la ventana de la aplicación con Wayland y el juego (Wine) con X11 (`DISPLAY=:0`); las dos salen en el escritorio de Windows.

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
| `FakeWine` | (clase) Sustituye a `wine`/`wineserver` en `PrefixManager`: `wineboot` crea `system.reg` y los `.exe` terminan con el código que se le indique |
| `wait_until` | (función) Procesa eventos de Qt hasta que se cumple una condición; para las tareas en segundo plano de la interfaz |

Las pruebas de la página Biblioteca (`tests/integration/test_library_page.py`) recorren el flujo completo con `FakeWine` y el intérprete de Python como «Wine»: añadir, comprobar, preparar el prefijo, lanzar, detener y guardar en el historial.

### Archivos de juegos en las pruebas

Los archivos reales de juegos **nunca** se suben al repositorio. Las pruebas generan juegos falsos al vuelo con `make_game` y `make_pe`, así que no hace falta ningún binario. Para pruebas manuales con juegos reales, guárdalos en `games/` (está en `.gitignore`) o fuera del repositorio.

### Pruebas con juegos reales

Son opcionales y en el CI se omiten. Se activan indicando la ruta de tu copia:

```bash
PTL_POKEMON_Z_PATH="/ruta/a/POKEMON Z V2.19" pytest -m realgame
PTL_POKEMON_Z_PATH="/ruta/a/POKEMON Z V2.19" xvfb-run -a pytest -m realgame   # sin pantalla
```

`test_pokemon_z_starts_with_wine` lanza el juego con su perfil en un **prefijo temporal** (nunca el tuyo, que tiene tus partidas), espera a que cree la ventana OpenGL, comprueba que sigue en marcha sin problemas en la salida y lo cierra. Tarda unos 2 minutos.

### Pruebas manuales en una pantalla virtual

`tools/manual-test/drive.sh` lanza el juego o la interfaz en un Xvfb y los maneja con teclas, clics y capturas. Así se recorre la [lista de funciones](compatibility.md#funciones-que-hay-que-probar) sin monitor (WSL, SSH, un servidor). Necesita `xvfb xdotool x11-apps imagemagick`:

```bash
export PTL_GAME=~/Juegos/"POKEMON Z V2.19" PTL_OUT=~/capturas
tools/manual-test/drive.sh start                       # Xvfb :95 y el juego con «run»
tools/manual-test/drive.sh keys w:5 Return w:3 Return  # título → «Continuar»
tools/manual-test/drive.sh shot continuar              # ~/capturas/continuar.png
tools/manual-test/drive.sh stop

tools/manual-test/drive.sh gui                         # la interfaz, en vez del juego
tools/manual-test/drive.sh click 300 56                # «Añadir juego…»
tools/manual-test/drive.sh type "$PTL_GAME"            # en el diálogo de carpetas
tools/manual-test/drive.sh screen biblioteca           # toda la pantalla
```

Notas:
- La interfaz se lanza con `QT_QPA_PLATFORM=xcb`: con WSLg, Qt elegiría Wayland y la ventana no saldría en el Xvfb.
- En WSL, Xvfb solo escucha en un socket abstracto (`@/tmp/.X11-unix/X95`), porque `/tmp/.X11-unix` es de WSLg. La comprobación de la sesión gráfica lo tiene en cuenta.
- En WSL, al manejar la interfaz desde Windows con varias llamadas a `wsl.exe`, a veces se cerraba al terminar una de ellas, aunque se lanzara con `setsid` (no se ha averiguado por qué). Con otra sesión abierta todo el rato (`wsl.exe -- sleep 3600`) no volvió a pasar.
- Sin gestor de ventanas, `drive.sh screen` puede mostrar en negro un diálogo que sí funciona; `drive.sh shot` (o `xwd -id`) lo captura bien.

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
pokemon-to-linux-cli check "/ruta/al/juego"  # ¿está todo listo para jugar? (--json)
pokemon-to-linux-cli run "/ruta/al/juego"    # prepara el prefijo y lanza el juego
pokemon-to-linux-cli run "/ruta/al/juego" --arch win32 --id mi-juego --timeout 60
pokemon-to-linux-cli profiles                # perfiles de compatibilidad cargados
pokemon-to-linux-cli library                 # juegos de la biblioteca (add <carpeta>, remove <id>)
```

`check` devuelve `0` si el juego está listo para jugar y `1` si falta algo. Además de la sesión gráfica, OpenGL y el sistema de ficheros, ejecuta el programa de prueba con los bits del juego: en el prefijo del juego si ya existe (unos segundos) o en uno temporal que borra después. Así, `wine64` sin `wine32:i386` da «Listo para jugar: no» en vez de fallar al lanzar.

`run` comprueba primero los requisitos del sistema. Si falta uno imprescindible (p. ej. OpenGL de 32 bits), explica cómo instalarlo y no lanza el juego; `--ignore-checks` lo lanza igualmente. Después aplica el perfil del juego, muestra dónde están las partidas y, al terminar, los problemas reconocidos en la salida con su solución.

Si la carpeta está en la biblioteca, `run` usa el identificador del juego en la biblioteca (y con él, su prefijo), también para una segunda copia del mismo juego (`pokemon-z-2`), y guarda el lanzamiento en su historial. `run` no crea la base de datos si no existe.

`run` devuelve el código de salida del juego. Si no terminó normalmente devuelve `1`, y si no se pudo lanzar, `2`.

Ctrl+C:
- **Con el juego en marcha**, lo detiene de forma ordenada (`wineserver -k`).
- **Mientras se prepara el prefijo**, cancela, borra el prefijo a medias y devuelve `130`.

- **Prefijos**: `~/.local/share/pokemon-to-linux/prefixes/<id>`. Las partidas suelen estar dentro (`drive_c/users/<usuario>/…`): no borres un prefijo sin copiarlas antes.
- **Perfiles del usuario**: `~/.config/pokemon-to-linux/profiles/*.toml` ([formato](profiles.md)).
- **Log de cada lanzamiento**: `~/.local/state/pokemon-to-linux/logs/games/<id>/<fecha>.log`. Se conservan los últimos 20 por juego.
- **Biblioteca**: `~/.local/share/pokemon-to-linux/library.sqlite3`. El esquema se actualiza solo al abrirla (`PRAGMA user_version`); una biblioteca de una versión más nueva de la aplicación no se toca.

## Integración continua

`.github/workflows/ci.yml` se ejecuta en cada push y en cada pull request.

**Job principal** (Ubuntu 24.04, Python 3.12 y 3.13):

1. Ruff (lint y formato)
2. pytest
3. Arranque real de la aplicación durante 5 s sin pantalla, comprobando el log
4. CLI, biblioteca (se crea al arrancar; `library` y `library add`), bibliotecas X11 completas y arranque en X11 (Xvfb)
5. Construcción del paquete (wheel)

**Job `wine`** (Ubuntu 24.04, Python 3.12):

1. Instala Wine 9.0 con `wine32:i386` y OpenGL de 32 bits (`libgl1:i386`, `libgl1-mesa-dri:i386`).
2. Comprueba con `wine --probe` que ejecuta 32 y 64 bits.
3. Comprueba que se detecta OpenGL de 32 y 64 bits y que los perfiles integrados son válidos.
4. Ejecuta `pytest -m wine`, que incluye lanzar el juego de prueba de extremo a extremo.

**Workflow `release`** (`.github/workflows/release.yml`, al subir una etiqueta `v*`):

1. Comprueba que la etiqueta coincide con la versión de `pyproject.toml` (`v0.1.0-alpha.1` ↔ `0.1.0a1`).
2. Construye el ejecutable con PyInstaller en **Ubuntu 22.04**, para que funcione con glibc 2.35 o más nueva.
3. Comprueba que arranca: `cli --version`, `cli profiles` y la interfaz 10 s en Xvfb.
4. Publica en la release de la etiqueta `pokemon-to-linux-<versión>-x86_64.tar.gz` (ejecutable, `install.sh`, `LEEME.txt`, `LICENSE`), el ejecutable suelto y `SHA256SUMS`. Si la etiqueta lleva guion (`-alpha.1`, `-rc.1`…), la marca como *pre-release*.

## Publicar una versión

1. Sube la versión en `pyproject.toml` (formato PEP 440: `0.1.0a1`, `0.1.0rc1`, `0.1.0`) y fusiona en `release`.
2. Prueba el ejecutable a mano: `pyinstaller --noconfirm packaging/pyinstaller/pokemon-to-linux.spec` y recorre añadir juego → Jugar → Detener (con `tools/manual-test/drive.sh gui` si no hay monitor).
3. Crea y sube la etiqueta: `git tag -a v0.1.0-alpha.1 -m "…" && git push origin v0.1.0-alpha.1`.
4. Cuando termine el workflow, completa las notas de la release (`gh release edit v0.1.0-alpha.1 --notes-file …`).

El ejecutable se ejecuta desde una carpeta temporal y la CLI va dentro con `cli` delante (`packaging/pyinstaller/launcher.py`). `packaging/linux/install.sh` lo copia a `~/.local/bin` y crea la entrada del menú en `~/.local/share/applications`.

## Convenciones

- Código, nombres y docstrings técnicos en inglés o español, pero de forma coherente dentro de cada módulo. Los textos de la interfaz y la documentación, en español.
- Logs: `get_logger(__name__)` en cada módulo.
- Procesos: listas de argumentos, nunca `shell=True` (Ruff lo comprueba con las reglas `S`).
- Cada sprint en su rama (`sprint1`, `sprint2`, …), que se fusiona en `master` al terminarlo.
