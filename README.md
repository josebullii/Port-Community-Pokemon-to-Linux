# Pokémon to Linux

[![CI](https://github.com/josebullii/Port-Community-Pokemon-to-Linux/actions/workflows/ci.yml/badge.svg)](https://github.com/josebullii/Port-Community-Pokemon-to-Linux/actions/workflows/ci.yml)
[![Licencia: GPL v3+](https://img.shields.io/badge/licencia-GPL--3.0--or--later-blue.svg)](LICENSE)

Lanzador y gestor de compatibilidad para ejecutar en Linux **fangames de Pokémon creados para Windows**, empezando por **Pokémon Z** (RPG Maker XP / Pokémon Essentials). El objetivo final es que también funcionen en consolas portátiles Linux como la **Anbernic R36S**.

> **Estado:** sprint 5 completado: **se puede jugar a Pokémon Z sin abrir una terminal**. En la ventana de la aplicación se añade la carpeta del juego, se ve si está listo para jugar (y qué falta si no), se pulsa «Jugar» y, al terminar, queda en el historial con los problemas reconocidos. La aplicación reconoce el juego por su perfil de compatibilidad, comprueba Wine y OpenGL de 32 bits, prepara un prefijo propio para el juego y lo lanza. Se ha probado en Ubuntu 24.04 sobre WSL2, con OpenGL por software (título, menús, exploración, guardar y cargar partida); faltan el combate, el audio y un Linux nativo con GPU. El sprint 6 se centra en estabilizar y publicar la versión 0.1.

---

## ¿Qué es y qué no es?

Pokémon to Linux **no reescribe** los juegos ni los convierte en ports nativos uno a uno. Automatiza lo que hoy se hace a mano:

1. Analizar la carpeta del juego y detectar el motor.
2. Preparar un entorno aislado para ese juego.
3. Lanzarlo y recoger información de diagnóstico.
4. Guardar la biblioteca, los perfiles y el historial de ejecuciones.

**Lo que el proyecto no hace:**

- No descarga ni redistribuye juegos, ROMs, recursos, DLL ni runtimes propietarios. **El usuario aporta su propia copia del juego.**
- No ejecuta scripts arbitrarios procedentes de perfiles de la comunidad.
- No instala Wine ni otras dependencias del sistema sin avisar.

---

## Juego de referencia: Pokémon Z v2.19

Análisis inicial de la carpeta del juego, que es la base para el detector:

| Elemento | Hallazgo |
|---|---|
| Motor | RPG Maker XP (RGSS1) + Pokémon Essentials (`Data/*.rxdata`, `PBS/`) |
| `Game.ini` | `Library=RGSS104E.dll`, `Scripts=Data\Scripts.rxdata` |
| DLL RGSS presentes | `RGSS102E.dll`, `RGSS102J.dll`, `RGSS104E.dll` |
| **`Game.exe`** | **Es [mkxp-z](https://github.com/mkxp-z/mkxp-z)** (PE32 i386, SDL2 2.0.12), no el reproductor RGSS original |
| Configuración del runtime | `mkxp.json` (vsync, blitting…) y `preload.rb` (parche de Zlib mediante `MKXP.zinflate`) |
| Recursos | `Graphics/`, `Audio/` (ogg/wav/mp3), `Fonts/` (8 fuentes TTF propias), `fluidsynth.dll` |
| Tamaño | ~915 MB |

### Por qué importa mkxp-z

mkxp-z es una reimplementación libre de RGSS con compilaciones nativas para Linux, incluido **ARM64 (aarch64)**. Esto abre dos vías de ejecución:

| Vía | Plataforma | Cómo |
|---|---|---|
| **Wine** | Linux x86_64 de escritorio | Ejecutar el `Game.exe` original en un prefijo Wine propio del juego. Es la vía del MVP. |
| **mkxp-z nativo** | Linux ARM (R36S y similares) y x86_64 | Sustituir `Game.exe` por un binario nativo de mkxp-z y reutilizar `Data/`, `Graphics/`, `Audio/`, `mkxp.json` y `preload.rb`. |

La R36S (Rockchip RK3326, ARM64, 640×480, controles de mando, sin escritorio) **no puede usar Wine de forma práctica**, así que la vía mkxp-z nativa es la que se seguirá para consolas. Hay que confirmar con pruebas que la versión de mkxp-z elegida es compatible con los scripts de Pokémon Z.

---

## Arquitectura

Arquitectura modular por capas. La interfaz nunca invoca Wine directamente: pide operaciones a la capa de aplicación.

| Capa | Responsabilidad |
|---|---|
| Presentación | Ventanas, biblioteca, formularios, ajustes y diagnóstico (PySide6). |
| Aplicación | Casos de uso: añadir, analizar, configurar, iniciar y detener juegos. |
| Dominio | Entidades y reglas: juego, motor, perfil y estado de compatibilidad. |
| Infraestructura | Wine, procesos, sistema de archivos, SQLite y registros. |
| Sistema Linux | Procesos, bibliotecas, audio, gráficos y escritorio. |

**Principios de diseño:**

- La interfaz está separada de la lógica de compatibilidad.
- Cada juego tiene su propio prefijo Wine.
- Cada motor es un módulo independiente que se puede ampliar.
- No se da por hecho que todos los juegos de RPG Maker XP necesiten la misma configuración.
- Las rutas y los argumentos se validan. Los comandos nunca se construyen concatenando cadenas ni con `shell=True`.
- Las operaciones largas se ejecutan fuera del hilo principal de la interfaz.

### Stack

| Área | Elección |
|---|---|
| Lenguaje | Python 3.12 |
| Interfaz | PySide6 + Qt Widgets |
| Compatibilidad | Wine (escritorio) · mkxp-z (ARM / consolas) |
| Persistencia | SQLite |
| Pruebas | pytest |
| Lint y formato | Ruff |
| Distribución | Por decidir después del MVP (posible Flatpak; paquete para PortMaster / R36S) |

### Estructura del repositorio

```
Port-Community-Pokemon-to-Linux/
├── pyproject.toml, README.md, LICENSE, .gitignore
├── .github/workflows/ci.yml
├── src/pokemon_to_linux/
│   ├── main.py, config.py
│   ├── ui/              # main_window, library_page, game_details, diagnostics_page, tasks
│   ├── application/     # analyze_game, library, check_requirements, launch_game, diagnose_output
│   ├── domain/          # game, profile, compatibility, requirements, dependencies
│   ├── infrastructure/
│   │   ├── database/    # connection, repositories
│   │   ├── wine/        # wine_manager, prefix_manager, process_manager
│   │   ├── filesystem/  # game_scanner, profile_store
│   │   ├── system/      # host (bibliotecas, sesión gráfica, montajes)
│   │   └── logging/     # logger
│   ├── engines/         # base, detector, rpgmaker_xp/
│   ├── profiles/        # perfiles de compatibilidad integrados (*.toml)
│   └── resources/       # icons, styles
├── tests/               # unit, integration
├── tools/manual-test/   # drive.sh: pruebas manuales en una pantalla virtual
└── docs/                # architecture, compatibility, development, profiles
```

---

## Detección de RPG Maker XP

El detector combina varias pistas y devuelve un nivel de confianza. **No basta con encontrar `Game.exe`.**

| Pista | Uso |
|---|---|
| `Game.exe` | Posible ejecutable principal. Por sí solo no identifica el motor. Se comprueba si es mkxp-z. |
| `Game.ini` | Configuración y referencia al runtime (`Library=`). |
| `RGSS*.dll` | Indica el runtime RGSS. Se revisan el nombre, la versión y la arquitectura. RGSS1 (XP) ≠ RGSS2 (VX). |
| `Data/*.rxdata` | Datos con el formato propio de RPG Maker XP. |
| `Graphics/`, `Audio/` | Habituales en estos juegos, pero no son concluyentes. |
| `mkxp.json`, `preload.rb` | Indican que el juego ya trae el runtime mkxp-z. |
| Dependencias PE | Sirven para saber la arquitectura y las bibliotecas que necesita. |

Ejemplo de resultado:

```json
{
  "detected": true,
  "engine": "rpgmaker_xp",
  "confidence": 0.95,
  "executable": "Game.exe",
  "runtime": "mkxp-z",
  "warnings": []
}
```

---

## Integración con Wine

- Comprueba que Wine está instalado y consulta su versión. **No lo instala sin avisar.**
- Crea un `WINEPREFIX` para cada juego. Por defecto es **win64**, que con soporte de 32 bits ejecuta también juegos de 32 bits como Pokémon Z; win32 es opcional.
- Antes de usar un prefijo nuevo, **ejecuta un programa de prueba** para confirmar que Wine puede ejecutar los bits del juego. Si falta `wine32`, lo explica.
- Lanza el juego con `QProcess`: captura stdout y stderr, guarda el código de salida y la duración, y cierra el juego y sus procesos hijos de forma ordenada (`wineserver -k`).
- El juego se queda en la carpeta que elija el usuario. No hace falta copiarlo.

Las decisiones técnicas están detalladas en [docs/architecture.md](docs/architecture.md#integración-con-wine-sprint-3).

### Rutas (XDG)

| Ruta | Contenido |
|---|---|
| `~/.local/share/pokemon-to-linux/` | Datos persistentes y prefijos |
| `~/.config/pokemon-to-linux/` | Preferencias |
| `~/.cache/pokemon-to-linux/` | Caché que se puede regenerar |
| `~/.local/state/pokemon-to-linux/` | Registros y estado |

### Modelo de datos (SQLite)

La biblioteca está en `~/.local/share/pokemon-to-linux/library.sqlite3`:

| Tabla | Campos |
|---|---|
| `games` | id (también el nombre de su prefijo de Wine), name, path, engine, runtime, bits, added_at |
| `launches` | id, game_id, started_at, duration, state, exit_code, error, log_file, problems |

Los perfiles de compatibilidad no van en la base de datos: son ficheros TOML ([formato](docs/profiles.md)). Las veces jugado, el tiempo de juego y la última vez se calculan del historial. Las partidas guardadas se quedan en el formato y la ubicación que usa el propio juego; SQLite no las almacena.

---

## Flujo de uso

1. **Seleccionar**: el usuario elige la carpeta del juego.
2. **Analizar**: el escáner revisa los archivos, la configuración y los ejecutables, y reconoce el motor.
3. **Guardar**: el juego se añade a la biblioteca (SQLite) solo si se reconoce el motor.
4. **Verificar**: se busca su perfil de compatibilidad y se comprueban la sesión gráfica, OpenGL con los bits del juego y la carpeta.
5. **Preparar**: al jugar, se comprueba Wine, se crea el prefijo la primera vez y se prueba que ejecuta los bits del juego.
6. **Jugar**: se lanza el juego y se reconocen los problemas conocidos en su salida.
7. **Registrar**: el resultado y los problemas quedan en el historial del juego.

La ficha del juego muestra su estado: *comprobando*, *listo para jugar*, *falta algo* (con qué y cómo resolverlo), *la carpeta ya no está*, *preparando*, *en marcha* o *deteniendo*. La compatibilidad (*no probado*, *no funciona*, *parcial*, *compatible*) viene de su perfil.

---

## Desarrollo

### Requisitos

- Linux x86_64 (para la vía Wine)
- Python 3.12 o superior
- Bibliotecas X11 que necesita Qt 6
- Git
- Wine **con soporte de 32 bits** y **OpenGL de 32 bits** (Pokémon Z es un programa de 32 bits que dibuja con OpenGL). Se instalan desde los repositorios de tu distribución; ver [docs/development.md](docs/development.md#wine-desde-el-sprint-3).

En Debian / Ubuntu:

```bash
sudo apt install python3 python3-venv python3-pip \
  libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xkb1
```

Los comandos para Fedora y Arch, y la solución al error *"Could not load the Qt platform plugin xcb"*, están en [docs/development.md](docs/development.md).

### Puesta en marcha

```bash
git clone https://github.com/josebullii/Port-Community-Pokemon-to-Linux.git
cd Port-Community-Pokemon-to-Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### Ejecutar

```bash
pokemon-to-linux          # o bien: python -m pokemon_to_linux
```

Los registros se guardan en `~/.local/state/pokemon-to-linux/logs/`.

### Jugar desde la interfaz

1. **Añadir juego…** y elige la carpeta del juego (la que tiene `Game.exe`, `Game.ini` y `Data/`). El juego no se copia ni se modifica.
2. La ficha del juego dice si está **listo para jugar** y, si no, qué falta y cómo instalarlo (Wine, OpenGL de 32 bits…). También muestra la compatibilidad según su perfil, dónde quedan las partidas, el historial y los problemas conocidos del juego.
3. **Jugar**. La primera vez se crea el prefijo de Wine del juego (unos 25 s hasta el título de Pokémon Z). Si falta algo imprescindible, pregunta antes de lanzarlo.
4. Al terminar (o con **Detener**), el lanzamiento queda en el historial con los problemas reconocidos en la salida del juego y su solución. **Ver último log** abre el log completo.

**Quitar de la biblioteca** no borra nada del disco: ni la carpeta del juego ni su prefijo (con las partidas). Si lo vuelves a añadir, recuperas las partidas.

Desde la terminal, la misma biblioteca:

```bash
pokemon-to-linux-cli library                    # lista los juegos
pokemon-to-linux-cli library add "/ruta/al/juego"
pokemon-to-linux-cli library remove pokemon-z   # no borra la carpeta ni el prefijo
```

### Analizar un juego

```bash
pokemon-to-linux-cli analyze "/ruta/a/POKEMON Z V2.19"          # informe legible
pokemon-to-linux-cli analyze "/ruta/a/POKEMON Z V2.19" --json   # JSON
```

```
  Motor:       RPG Maker XP (detectado, confianza 100%)
  Runtime:     mkxp-z (SDL2 2.0.12)
  RGSS:        RGSS104E.dll (versión 1.04, i386)
  Ejecutable:  Game.exe (i386, 32 bits, gui)
  OpenGL:      sí
  DLL:         16 de sistema, 0 incluidas, 0 redistribuibles, 0 faltan
```

El informe completo de Pokémon Z está en [docs/compatibility.md](docs/compatibility.md).

### Jugar con Wine

En Debian / Ubuntu, Pokémon Z necesita:

```bash
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install wine wine64 wine32:i386 libgl1:i386 libgl1-mesa-dri:i386
```

```bash
pokemon-to-linux-cli check "/ruta/a/POKEMON Z V2.19"   # ¿está todo listo para jugar?
pokemon-to-linux-cli run "/ruta/a/POKEMON Z V2.19"     # prepara el prefijo y lanza el juego
```

```
  Juego:       pokemon-z
  Perfil:      Pokémon Z · Parcial
  Ejecutable:  /home/yo/Juegos/POKEMON Z V2.19/Game.exe
  Prefijo:     ~/.local/share/pokemon-to-linux/prefixes/pokemon-z (win64)
  Partidas:    ~/.local/share/pokemon-to-linux/prefixes/pokemon-z/drive_c/users/yo/Saved Games/Pokemon Z
```

- **Requisitos.** `run` comprueba antes la sesión gráfica, OpenGL con los bits del juego y si la carpeta está en un sistema de ficheros lento (p. ej. `/mnt/c` en WSL). Si falta algo imprescindible, explica cómo instalarlo y no lanza el juego.
- **Perfiles.** El [perfil de Pokémon Z](src/pokemon_to_linux/profiles/pokemon-z.toml) indica la arquitectura del prefijo, dónde guarda las partidas y sus problemas conocidos. Puedes añadir los tuyos en `~/.config/pokemon-to-linux/profiles/` ([formato](docs/profiles.md)).
- **Partidas.** Con Wine, las partidas quedan **dentro del prefijo del juego**. No lo borres sin copiarlas antes.
- **Diagnóstico.** Al terminar, `run` explica los problemas reconocidos en la salida del juego (falta OpenGL de 32 bits, wine32, una DLL, el audio…) y cómo resolverlos.

Si la carpeta está en la biblioteca, `run` usa el mismo prefijo que la interfaz y guarda el lanzamiento en el historial.

La primera vez se crea el prefijo del juego, lo que tarda unos segundos. Cada ejecución deja un log en `~/.local/state/pokemon-to-linux/logs/games/<id>/`, donde se conservan los 20 últimos. Ctrl+C detiene el juego de forma ordenada, cerrando también sus procesos secundarios.

### Pruebas y lint

```bash
pytest
ruff check .
ruff format .
```

La [integración continua](.github/workflows/ci.yml) ejecuta en cada push Ruff, pytest, un arranque real de la aplicación y la construcción del paquete en **Ubuntu 24.04 con Python 3.12 y 3.13**.

### Documentación

- [Arquitectura](docs/architecture.md): capas, módulos y rutas
- [Compatibilidad](docs/compatibility.md): matriz de pruebas y ficha de Pokémon Z
- [Desarrollo](docs/development.md): requisitos, pruebas, CI y convenciones
- [Perfiles](docs/profiles.md): formato de los perfiles de compatibilidad

| Nivel | Qué cubre |
|---|---|
| Unitarias | Detección, lectura de INI, validación de rutas, perfiles y repositorios |
| Integración | Wine, creación de prefijos, ejecución de binarios de prueba y gestión de procesos |
| Funcionales | Pokémon Z: inicio, menús, exploración, combates, audio, guardado, carga y estabilidad |

Cada prueba registra el juego y su versión, el motor, la distribución, la arquitectura, la versión de Wine o mkxp-z, la configuración y el resultado. **Que un juego arranque no basta para declararlo compatible.**

> Los archivos de juegos **nunca** se suben al repositorio. En los tests se usan *fixtures* mínimos creados a propósito.

---

## Hoja de ruta

| Sprint | Trabajo | Entregable |
|---|---|---|
| 1 · Fundación ✅ | Repositorio, `pyproject.toml`, PySide6, ventana, logging, tests base | La aplicación arranca |
| 2 · Análisis ✅ | Escáner, lectura de `Game.ini`, detector XP/mkxp-z | Diagnóstico de Pokémon Z |
| 3 · Wine ✅ | WineManager, PrefixManager, QProcess, logs | Juego de prueba lanzado desde Python |
| 4 · Juego real ✅ | Perfil de Pokémon Z, dependencias, pruebas de juego | Pokémon Z se ejecuta por primera vez |
| 5 · Biblioteca ✅ | SQLite, alta de juegos, biblioteca, detalles, diagnóstico | Lanzador completo de principio a fin |
| 6 · Estabilización | Cierres, fallos, documentación, versión 0.1 | MVP listo para pruebas de la comunidad |

### Primer hito

El hito se cumple cuando cualquier persona puede seleccionar la carpeta de Pokémon Z, recibir un diagnóstico comprensible, preparar el entorno y **ejecutar el juego sin abrir una terminal**. El informe de pruebas indicará qué funciones se han validado y cuáles quedan pendientes.

### Después del MVP

- **Port para consolas ARM (R36S)**: empaquetar con mkxp-z nativo para aarch64, mapear los controles del mando, ajustar a 640×480 y generar un lanzador compatible con PortMaster / ArkOS.
- Más motores de fangames de Pokémon (RPG Maker VX/VX Ace, Pokémon Essentials en sus distintas versiones…).
- Perfiles de compatibilidad compartidos y versionados (declarativos, validados y sin scripts).
- Informes de la comunidad y resultados reproducibles.
- Copias de seguridad de partidas y perfiles.
- Paquetes de distribución (Flatpak, etc.) y pruebas en más distribuciones.

---

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Runtime RGSS ausente o incompatible | Analizar el juego y dar una guía para instalar los componentes de forma legal |
| Arquitectura de 32 o 64 bits | Analizar el PE y probar prefijos compatibles |
| Problemas de audio o gráficos | Pruebas funcionales y perfiles específicos por juego |
| Wine no está instalado | Detectarlo claramente y explicar cómo instalarlo desde la distribución |
| Procesos hijo que siguen activos | Seguir los procesos y cerrarlos de forma ordenada |
| Perfiles de la comunidad inseguros | Formato declarativo, validación y revisión |
| mkxp-z en ARM incompatible con algún script | Probar por juego y fijar la versión de mkxp-z en el perfil |

Problemas conocidos de Pokémon Z en PC, según la documentación del propio juego:

- El juego va demasiado rápido: desactivar VSync en las opciones del juego.
- El juego se cierra al sacar un Pokémon: desactivar los sprites animados.
- Error `NameError` en Random: el sistema usa una configuración regional que no es española. En Wine, probar con `LANG=es_ES.UTF-8`.

---

## Legal

- Pokémon es una marca de Nintendo, Game Freak y The Pokémon Company. Este proyecto no está afiliado a ellas.
- Los fangames pertenecen a sus creadores (p. ej., Pokémon Z, de Eric Lostie). Este repositorio **no incluye** ningún juego ni ninguno de sus recursos.
- Las dependencias se obtienen siempre de sus fuentes oficiales.

## Referencias

- [Qt for Python / PySide6](https://doc.qt.io/qtforpython/)
- [Documentación de Wine](https://www.winehq.org/documentation)
- [mkxp-z](https://github.com/mkxp-z/mkxp-z)
- [Especificación XDG Base Directory](https://specifications.freedesktop.org/basedir-spec/latest/)
- [pytest](https://docs.pytest.org/)
- [Flatpak](https://docs.flatpak.org/)
- [PortMaster](https://portmaster.games/)

## Licencia

Copyright (C) 2026 Jose Pulido Diaz

Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo los términos de la **GNU General Public License** publicada por la Free Software Foundation, ya sea la **versión 3** de la licencia o (a tu elección) cualquier versión posterior (`GPL-3.0-or-later`).

Se distribuye con la esperanza de que sea útil, pero **SIN NINGUNA GARANTÍA**. Consulta el archivo [`LICENSE`](LICENSE) para ver el texto completo.

> La licencia solo cubre el código de este repositorio. Los fangames, sus recursos y los runtimes de terceros (p. ej. mkxp-z, también GPL) tienen sus propias licencias y sus propios autores.
