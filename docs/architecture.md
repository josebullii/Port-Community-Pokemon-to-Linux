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
| `infrastructure/filesystem/` | `GameScanner`: inventario de la carpeta de un juego | 2 |
| `engines/` | `EngineDetector` base + `rpgmaker_xp/` (RGSS1, mkxp-z) | 2 |
| `infrastructure/wine/` | `WineManager`, `PrefixManager`, `ProcessManager` (`QProcess`) | 3 |
| `domain/` | Entidades `Game`, `Engine`, `Profile`, estado de compatibilidad | 4 |
| `infrastructure/database/` | Conexión SQLite y repositorios | 5 |
| `application/` | Casos de uso que orquestan todo lo anterior | 5 |

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
