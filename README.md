# Pokémon to Linux

[![CI](https://github.com/josebullii/Port-Community-Pokemon-to-Linux/actions/workflows/ci.yml/badge.svg)](https://github.com/josebullii/Port-Community-Pokemon-to-Linux/actions/workflows/ci.yml)
[![Licencia: GPL v3+](https://img.shields.io/badge/licencia-GPL--3.0--or--later-blue.svg)](LICENSE)

Lanzador y gestor de compatibilidad para ejecutar en Linux **fangames de Pokémon creados para Windows**, empezando por **Pokémon Z** (RPG Maker XP / Pokémon Essentials). El objetivo final es que también funcionen en consolas portátiles Linux como la **Anbernic R36S**.

> **Estado:** sprint 1 (fundación) completado: la aplicación arranca con ventana, logging y pruebas base. Aún no analiza ni lanza juegos.

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

### Estructura del repositorio (prevista)

```
Port-Community-Pokemon-to-Linux/
├── pyproject.toml, README.md, LICENSE, .gitignore
├── .github/workflows/ci.yml
├── src/pokemon_to_linux/
│   ├── main.py, config.py
│   ├── ui/              # main_window, library_page, add_game_dialog, settings
│   ├── application/     # add_game, analyze_game, configure_game, launch_game, stop_game
│   ├── domain/          # game, engine, profile, compatibility
│   ├── infrastructure/
│   │   ├── database/    # connection, repositories
│   │   ├── wine/        # wine_manager, prefix_manager, process_manager
│   │   ├── filesystem/  # game_scanner
│   │   └── logging/     # logger
│   ├── engines/         # base, detector, rpgmaker_xp/
│   └── resources/       # icons, styles
├── tests/               # unit, integration, fixtures
└── docs/                # architecture, compatibility, development
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
- Crea un `WINEPREFIX` para cada juego. La arquitectura (win32 o WoW64) se elige después de analizar el ejecutable. win32 no es una regla fija.
- Lanza el juego con `QProcess`: captura stdout y stderr, guarda el código de salida y la duración, y cierra los procesos hijos de forma ordenada.
- El juego se queda en la carpeta que elija el usuario. No hace falta copiarlo.

### Rutas (XDG)

| Ruta | Contenido |
|---|---|
| `~/.local/share/pokemon-to-linux/` | Datos persistentes y prefijos |
| `~/.config/pokemon-to-linux/` | Preferencias |
| `~/.cache/pokemon-to-linux/` | Caché que se puede regenerar |
| `~/.local/state/pokemon-to-linux/` | Registros y estado |

### Modelo de datos (SQLite)

| Tabla | Campos principales |
|---|---|
| `games` | id, name, game_path, executable, engine_id, created_at |
| `engines` | id, name, version |
| `profiles` | id, game_id, wine_version, prefix_path, architecture, configuration |
| `launch_history` | id, game_id, started_at, ended_at, exit_code, status |

Las partidas guardadas se quedan en el formato y la ubicación que usa el propio juego. SQLite no las almacena.

---

## Flujo de uso

1. **Seleccionar**: el usuario elige la carpeta del juego.
2. **Analizar**: el escáner revisa los archivos, la configuración y los ejecutables.
3. **Identificar**: se propone el motor, con su nivel de confianza y las advertencias.
4. **Verificar**: se comprueban Wine (o mkxp-z), la arquitectura y las dependencias.
5. **Preparar**: se crea el prefijo y se aplica la configuración inicial.
6. **Probar**: se lanza el juego y se recoge el diagnóstico.
7. **Guardar**: el juego, el perfil y el resultado se registran en SQLite.

La interfaz muestra estados precisos: *no analizado, detectado, configurado, probado, compatible parcialmente, con errores*.

---

## Desarrollo

### Requisitos

- Linux x86_64 (para la vía Wine)
- Python 3.12 o superior
- Bibliotecas X11 que necesita Qt 6
- Git
- Wine, solo a partir del sprint 3. Se instala desde los repositorios de tu distribución.

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
| 1 · Fundación | Repositorio, `pyproject.toml`, PySide6, ventana, logging, tests base | La aplicación arranca |
| 2 · Análisis | Escáner, lectura de `Game.ini`, detector XP/mkxp-z | Diagnóstico de Pokémon Z |
| 3 · Wine | WineManager, PrefixManager, QProcess, logs | Juego de prueba lanzado desde Python |
| 4 · Juego real | Perfil de Pokémon Z, dependencias, pruebas de juego | Pokémon Z se ejecuta por primera vez |
| 5 · Biblioteca | SQLite, alta de juegos, biblioteca, detalles, diagnóstico | Lanzador completo de principio a fin |
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
