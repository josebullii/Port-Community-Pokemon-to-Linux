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
| `infrastructure/wine/wine_manager.py` | `WineManager`: localiza Wine (PATH, `/usr/lib/wine`, `/opt/wine-*`), su versión y `wineserver`. `wine_environment` prepara el entorno | 3 ✅ |
| `infrastructure/wine/prefix_manager.py` | `PrefixManager`: un prefijo por juego. Lo crea, reutiliza, prueba y borra | 3 ✅ |
| `infrastructure/wine/process_manager.py` | `GameProcess` y `ProcessManager`: QProcess, salida línea a línea, log por lanzamiento y cierre ordenado | 3 ✅ |
| `infrastructure/wine/test_program.py` | Genera un `.exe` mínimo real (32 o 64 bits) que termina con un código dado | 3 ✅ |
| `application/launch_game.py` | `prepare_launch` (aplica el perfil), `launch_game` y `stop_game` | 3-4 ✅ |
| `domain/compatibility.py` | `CompatibilityStatus`: no probado, no funciona, parcial, compatible | 4 ✅ |
| `domain/profile.py` | `GameProfile` y su validación (`parse_profile`), `select_profile` | 4 ✅ |
| `domain/requirements.py` | `RequirementCheck` y `CheckStatus` (ok, aviso, error, desconocido) | 4 ✅ |
| `profiles/*.toml` | Perfiles integrados: [Pokémon Z](../src/pokemon_to_linux/profiles/pokemon-z.toml) | 4 ✅ |
| `infrastructure/filesystem/profile_store.py` | Carga los perfiles integrados y los del usuario (`~/.config/…/profiles`) | 4 ✅ |
| `infrastructure/system/host.py` | `HostSystem`: bibliotecas (`ldconfig -p`), sesión gráfica y sistema de ficheros de cada carpeta | 4 ✅ |
| `application/profiles.py` | `match_profile` y `resolve_folder` (carpetas de partidas dentro del prefijo) | 4 ✅ |
| `application/check_requirements.py` | Sesión gráfica, OpenGL con los bits del juego y sistema de ficheros lento | 4 ✅ |
| `application/diagnose_output.py` | `OutputDiagnoser`: problemas conocidos en la salida del juego | 4 ✅ |
| `cli.py` | Comandos `check` y `profiles`; `run` comprueba requisitos y diagnostica | 4 ✅ |
| `infrastructure/database/` | Conexión SQLite y repositorios | 5 |
| `application/` (resto) | Casos de uso para añadir y configurar juegos | 5 |

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
| `profiles_dir` | `~/.config/pokemon-to-linux/profiles/` | Perfiles de compatibilidad del usuario |
| `cache_dir` | `~/.cache/pokemon-to-linux/` | Caché que se puede regenerar |
| `state_dir` / `log_dir` | `~/.local/state/pokemon-to-linux/logs/` | Registros |

Se respetan `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` y `XDG_STATE_HOME`. Como pide la especificación, las rutas relativas se ignoran.

## Dos vías de ejecución

| Vía | Plataforma | Estado |
|---|---|---|
| Wine + `Game.exe` original | Linux x86_64 de escritorio | MVP. Pokémon Z funciona desde el sprint 4 |
| mkxp-z nativo | Linux ARM64 (R36S) y x86_64 | Después del MVP |

Pokémon Z v2.19 ya incluye mkxp-z como `Game.exe`, junto con `mkxp.json` y `preload.rb`. Ver [compatibility.md](compatibility.md).

## Integración con Wine (sprint 3)

```
prepare_launch(carpeta)
  ├─ analyze_game            → ejecutable, bits (sprint 2)
  ├─ resolve_arch            → win64 (por defecto) o win32
  ├─ PrefixManager.ensure    → prefixes/<id>   (wineboot --init + wineserver -w)
  ├─ run_test_program        → solo si el prefijo es nuevo: ¿ejecuta N bits?
  └─ LaunchSpec              → wine Game.exe, WINEPREFIX…, stop = wineserver -k
launch_game(plan) → ProcessManager → GameProcess (QProcess) → log por lanzamiento
```

Decisiones, comprobadas con Wine 9.0 en Ubuntu 24.04:

| Decisión | Motivo |
|---|---|
| **Prefijo win64 por defecto, también para juegos de 32 bits** | Con soporte de 32 bits, win64 (WoW64) ejecuta 32 y 64 bits. Los Wine solo-WoW64 ya no crean prefijos win32. win32 queda como opción (`--arch win32`) y se rechaza para ejecutables de 64 bits. |
| **El soporte de 32 bits se prueba, no se deduce** | Que existan los paquetes no garantiza nada: `wine64` sin `wine32` ejecuta 64 bits pero falla con 32 (`syswow64\ntdll.dll` no encontrado). Por eso se ejecuta un programa de prueba real. |
| **`wineserver -w` tras `wineboot --init`** | `wineboot` termina antes de que `system.reg` esté en disco. |
| **Parar con `wineserver -k`** | El juego no es hijo directo del proceso `wine`. Terminar `wine` no lo cierra; `wineserver -k` cierra todo el prefijo. Si no basta, se fuerza el cierre tras 5 s. |
| **`WINEDLLOVERRIDES=mscoree=;mshtml=`** | Evita que Wine ofrezca instalar Mono o Gecko con ventanas emergentes. |
| **Se descartan los `WINE*` del entorno del usuario** | Un `WINEPREFIX` o un `WINEARCH` propios no deben mezclarse con el prefijo del juego. |
| **Nunca se recrea ni se borra un prefijo sin pedirlo** | `ensure` falla si el prefijo existe con otra arquitectura. `delete` no sigue enlaces simbólicos. |
| **Los prefijos a medias o fallidos se borran** | Si `wineboot` falla o se interrumpe (incluido Ctrl+C), o si el prefijo nuevo no supera el programa de prueba, se borra. Si se quedara, el siguiente intento lo reutilizaría sin comprobarlo o fallaría con "no se sobrescribe". |
| **Logs por lanzamiento con retención** | `logs/games/<id>/<fecha>.log`, con nombres únicos. Se conservan los últimos 20 por juego. |

Comprobado con Wine real (prueba `test_stop_game_closes_game_and_secondary_processes`): `stop_game` cierra el juego y otro programa lanzado aparte en el mismo prefijo antes de que actúe el cierre forzado, y después no queda ningún proceso en el prefijo.

**Pendiente para el sprint 5 (interfaz):**
- La página "Diagnóstico" ejecuta `wine --version` y `ldconfig -p` (OpenGL, desde el sprint 4) en el hilo de la interfaz. Tardan milisegundos, pero si se colgaran bloquearían la ventana hasta 30 y 15 s.
- `prepare_launch` puede tardar segundos (crear el prefijo) y tendrá que ejecutarse en un hilo de trabajo.

### Programa de prueba

`test_program.py` genera byte a byte un ejecutable PE real de 32 o 64 bits que llama a `kernel32!Sleep(ms)` y después a `kernel32!ExitProcess(código)`. Con `sleep_ms` grande sirve para probar cómo se detiene un programa en marcha. Así se puede comprobar Wine y probar el lanzador de extremo a extremo sin compiladores, sin binarios en el repositorio y sin juegos con copyright.

## Perfiles, requisitos y diagnóstico (sprint 4)

```
run <carpeta>
  ├─ load_profiles              → integrados + ~/.config/…/profiles (los rotos se avisan)
  ├─ analyze_game
  ├─ check_requirements         → sesión gráfica, OpenGL de N bits, sistema de ficheros
  │                               (un error bloquea, salvo --ignore-checks)
  ├─ prepare_launch(profiles=…) → match_profile: arquitectura, entorno, carpetas de partidas
  └─ launch_game + OutputDiagnoser
                                → al terminar: mensajes esperados y problemas, con solución
```

Decisiones, comprobadas con Pokémon Z en Ubuntu 24.04 (WSL2) y Wine 9.0:

| Decisión | Motivo |
|---|---|
| **Comprobar OpenGL con los bits del juego antes de lanzar** | Fue el primer fallo real: Pokémon Z es de 32 bits e importa `opengl32.dll`, que Wine implementa con la `libGL.so.1` de 32 bits del sistema. `wine32:i386` no la instala con `--no-install-recommends`, y mkxp-z falla con *No matching GL pixel format available*. |
| **`ldconfig -p`, no rutas fijas** | Cada distribución pone las bibliotecas de 32 bits en un sitio (`/usr/lib/i386-linux-gnu`, `/usr/lib32`, `/usr/lib`). `ldconfig` sabe cuáles son de 32 bits. Se busca también en `/usr/sbin`, que en Debian no está en el `PATH` de los usuarios. Con libglvnd hace falta además un `libGLX_<driver>.so.0` de los mismos bits. |
| **Lo que no se puede comprobar no bloquea** | Sin `ldconfig` (NixOS, musl…) el estado es "desconocido" y el juego se lanza. |
| **Aviso, no error, por sistema de ficheros lento** | Desde `/mnt/c` de WSL (9P), Pokémon Z tarda unos 2,5 minutos en mostrar el título; desde ext4, unos 20 s. Funciona, pero parece colgado. |
| **Perfiles como datos validados** | Una lista cerrada de variables de entorno (nada de `LD_PRELOAD`, `PATH` ni `WINE*`), rutas de partidas que no salen de su carpeta y patrones de salida literales (nada de expresiones regulares). Formato: [profiles.md](profiles.md). |
| **Las partidas están dentro del prefijo** | Pokémon Essentials guarda en `%USERPROFILE%\Saved Games\<juego>`, que con Wine es `<prefijo>/drive_c/users/<usuario>/Saved Games/<juego>`. El perfil lo declara y `run` lo muestra: borrar el prefijo borraría las partidas. |
| **`WINEDEBUG=fixme-all` al jugar** | Con `-all` se perdían los `err` de Wine, que dicen la causa exacta (p. ej. `Failed to load libGL`). Los `fixme` siguen ocultos porque son ruido. |
| **Problemas del perfil antes que los generales** | Así un perfil puede declarar como inofensivo (`harmless`) un mensaje que en general sería un error: en Pokémon Z, las DLL que le faltan a `fluidsynth.dll` (no tiene MIDI). |

## Principios

- Cada juego tiene su propio prefijo Wine. No se comparten DLL ni configuración entre juegos.
- Cada motor es un módulo independiente. No se da por hecho que todos los juegos de RPG Maker XP se configuren igual.
- Los procesos se lanzan con `QProcess` o `subprocess` pasando listas de argumentos. **Nunca `shell=True` ni comandos concatenados.**
- Las operaciones largas se ejecutan fuera del hilo de la interfaz.
- Los perfiles de la comunidad son datos declarativos que se validan antes de usarlos. Nunca se ejecutan como scripts.
