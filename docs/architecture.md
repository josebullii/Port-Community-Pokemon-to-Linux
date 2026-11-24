# Arquitectura

Pokémon to Linux es un lanzador y gestor de compatibilidad. No reescribe los juegos: los analiza, prepara un entorno aislado (Wine o mkxp-z) y los lanza.

## Capas

```
┌──────────────────────────────────────────────┐
│ Presentación   ui/            (PySide6)      │  ventanas, biblioteca, diagnóstico
├──────────────────────────────────────────────┤
│ Aplicación     application/                  │  casos de uso: añadir, analizar,
│                                              │  configurar, lanzar, detener
├──────────────────────────────────────────────┤
│ Dominio        domain/, engines/             │  juego, motor, perfil, compatibilidad
├──────────────────────────────────────────────┤
│ Infraestructura infrastructure/              │  Wine, procesos, ficheros, SQLite, logs
└──────────────────────────────────────────────┘
                 Sistema Linux
```

**Regla de dependencias:** cada capa solo usa las capas que tiene debajo. La interfaz nunca llama a Wine ni a SQLite: pide un caso de uso a `application/`.

## Módulos

| Ruta | Responsabilidad | Sprint |
|---|---|---|
| `main.py` | Punto de entrada: rutas XDG, logging, `QApplication`, ventana | 1 ✅ |
| `config.py` | `AppPaths`: rutas XDG de la app (datos, config, caché, estado, prefijos, BD, logs) | 1 ✅ |
| `infrastructure/logging/` | Log rotativo en fichero + consola, `excepthook` global | 1 ✅ |
| `ui/main_window.py` | Ventana principal: Biblioteca, Diagnóstico, Acerca de | 1 ✅ |
| `infrastructure/filesystem/game_scanner.py` | `GameScanner`: inventario de la carpeta. Búsquedas sin distinguir mayúsculas, sin seguir enlaces simbólicos ni junctions de NTFS, y con límite de ficheros | 2 ✅ |
| `domain/dependencies.py` | Clasifica las DLL importadas: incluidas, de sistema, redistribuibles o que faltan | 2 ✅ |
| `infrastructure/filesystem/ini_reader.py` | Lectura de `Game.ini`: detecta UTF-8, Shift-JIS o cp1252 y normaliza claves | 2 ✅ |
| `infrastructure/filesystem/pe_inspector.py` | Cabeceras PE: arquitectura, 32/64 bits, DLL importadas y marcadores binarios | 2 ✅ |
| `engines/base.py`, `engines/detector.py` | Contrato `EngineDetector` y `DetectionResult`. `detect_engine` elige el mejor resultado | 2 ✅ |
| `engines/rpgmaker_xp/` | `RPGMakerXPDetector`: indicios con peso, runtime (mkxp-z, mkxp, rgss1) y advertencias | 2 ✅ |
| `application/analyze_game.py` | Caso de uso `analyze_game`: escaneo, detección y advertencias | 2 ✅ |
| `cli.py` | `pokemon-to-linux-cli analyze <carpeta> [--json]` | 2 ✅ |
| `infrastructure/wine/` | `WineManager`, `PrefixManager`, `ProcessManager` (`QProcess`) | 3 |
| `domain/` | Entidades `Game`, `Engine`, `Profile`, estado de compatibilidad | 4 |
| `infrastructure/database/` | Conexión SQLite y repositorios | 5 |
| `application/` (resto) | Casos de uso para añadir, configurar, lanzar y detener juegos | 3-5 |

## Detección de motor (sprint 2)

```
carpeta ──► GameScanner ──► GameScan ──► detect_engine ──► DetectionResult
                                          │
                                          └─ RPGMakerXPDetector (+ futuros detectores)
```

`RPGMakerXPDetector` suma indicios con peso. El máximo es 1.0:

| Indicio | Peso |
|---|---|
| `Game.ini` con sección `[Game]` | +0.10 |
| `Library=` apunta a una DLL RGSS1 (`RGSS1xx*.dll`) | +0.25 |
| `Scripts=` apunta a un `.rxdata` | +0.15 |
| DLL RGSS1 presente en la carpeta | +0.15 |
| `Data/*.rxdata` o `Game.rgssad` | +0.25 |
| `Graphics/` y `Audio/` | +0.05 |
| Ejecutable PE válido | +0.05 |
| Indicios de VX o VX Ace (RGSS2/3, `.rvdata`, `.rvdata2`, `.rgss2a`, `.rgss3a`) | −0.30 |

Un juego se considera **detectado** si la confianza llega a 0.5 **y** hay al menos un indicio propio de XP: `.rxdata`, `.rgssad` o RGSS1 en el INI. Así, un `Game.exe` por sí solo nunca basta.

El runtime se identifica buscando marcadores dentro del ejecutable:
- `mkxp-z` → **mkxp-z**
- `mkxp` → **mkxp**
- ninguno de los dos, pero hay DLL RGSS1 → **rgss1**
- en cualquier otro caso → **unknown**

Con mkxp-z no se avisa de que falte la DLL indicada en `Library=`, porque no la usa.

### DLL RGSS

De cada `RGSS1xx*.dll` se obtienen:
- **Versión y edición**, a partir del nombre: `RGSS104E` es la 1.04, edición inglesa.
- **Validez y arquitectura**, a partir de la cabecera PE.

Si el runtime carga la DLL (`rgss1`), se avisa cuando:
- falta;
- está dañada o es un ejecutable en vez de una DLL;
- su arquitectura no coincide con la del ejecutable.

### Dependencias PE

Las DLL que importa el ejecutable (y la DLL RGSS, si se carga) se clasifican en el mismo orden en que Windows las busca:

1. `bundled`: en la carpeta del juego.
2. `system`: las trae Windows y Wine las implementa.
3. `redistributable`: Visual C++, DirectX, OpenAL…
4. `missing`: ninguna de las anteriores.

Las dos últimas generan advertencia.

## Rutas en tiempo de ejecución (XDG)

| `AppPaths` | Ruta por defecto | Contenido |
|---|---|---|
| `data_dir` | `~/.local/share/pokemon-to-linux/` | Datos persistentes |
| `prefixes_dir` | `…/share/pokemon-to-linux/prefixes/` | Un `WINEPREFIX` por juego |
| `database_path` | `…/share/pokemon-to-linux/library.sqlite3` | Biblioteca, perfiles, historial |
| `config_dir` | `~/.config/pokemon-to-linux/` | Preferencias |
| `cache_dir` | `~/.cache/pokemon-to-linux/` | Caché que se puede regenerar |
| `state_dir` / `log_dir` | `~/.local/state/pokemon-to-linux/logs/` | Registros |

Se respetan `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` y `XDG_STATE_HOME`. Como pide la especificación, las rutas relativas se ignoran.

## Dos vías de ejecución

| Vía | Plataforma | Estado |
|---|---|---|
| Wine + `Game.exe` original | Linux x86_64 de escritorio | MVP (sprints 3-4) |
| mkxp-z nativo | Linux ARM64 (R36S) y x86_64 | Después del MVP |

Pokémon Z v2.19 ya incluye mkxp-z como `Game.exe`, junto con `mkxp.json` y `preload.rb`. Ver [compatibility.md](compatibility.md).

## Principios

- Cada juego tiene su propio prefijo Wine. No se comparten DLL ni configuración entre juegos.
- Cada motor es un módulo independiente. No se da por hecho que todos los juegos de RPG Maker XP se configuren igual.
- Los procesos se lanzan con `QProcess` o `subprocess` pasando listas de argumentos. **Nunca `shell=True` ni comandos concatenados.**
- Las operaciones largas se ejecutan fuera del hilo de la interfaz.
- Los perfiles de la comunidad son datos declarativos que se validan antes de usarlos. Nunca se ejecutan como scripts.
