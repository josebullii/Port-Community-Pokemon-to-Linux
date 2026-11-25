# Perfiles de compatibilidad

Un perfil describe cómo reconocer un juego concreto y qué necesita para funcionar en Linux. Es un fichero TOML con **datos declarativos**: no puede ejecutar código, y se valida entero antes de usarse.

| Dónde | Para qué |
|---|---|
| `src/pokemon_to_linux/profiles/*.toml` | Perfiles integrados (se distribuyen con la aplicación) |
| `~/.config/pokemon-to-linux/profiles/*.toml` | Tus perfiles. Uno con el mismo `id` que un integrado lo sustituye |

```bash
pokemon-to-linux-cli profiles          # perfiles cargados y los que tienen errores
pokemon-to-linux-cli check <carpeta>   # qué perfil corresponde a un juego
```

Si un perfil tuyo tiene un error, se ignora y se avisa: un perfil roto no impide lanzar los demás juegos. Si el que falla es uno integrado, es un fallo del programa (lo detectan las pruebas y el CI).

## Ejemplo: Pokémon Z

```toml
schema = 1
id = "pokemon-z"
name = "Pokémon Z"
description = "Fangame de Pokémon Essentials sobre RPG Maker XP."

[match]
engine = "rpgmaker_xp"
runtimes = ["mkxp-z"]
titles = ["Pokemon Z"]

[wine]
arch = "win64"

[saves]
paths = ["%USERPROFILE%/Saved Games/Pokemon Z"]
config = ["%APPDATA%/Pokemon Z"]

[compatibility]
status = "partial"
notes = "Arranca y es jugable con Wine 9.0 en Ubuntu 24.04."

[[known_issues]]
id = "fluidsynth-sin-midi"
symptom = "fluidsynth.dll no se carga y la música MIDI queda desactivada."
solution = "No afecta: el juego no trae música MIDI."
output = ["fluidsynth.dll"]
harmless = true
```

El perfil completo está en [`pokemon-z.toml`](../src/pokemon_to_linux/profiles/pokemon-z.toml).

## Campos

Las claves desconocidas son un error, para que una errata no pase inadvertida.

### Raíz

| Campo | Obligatorio | Descripción |
|---|---|---|
| `schema` | sí | Versión del formato. Ahora, `1` |
| `id` | sí | Identificador: minúsculas, números, `.`, `-` y `_` (hasta 64) |
| `name` | sí | Nombre que se muestra |
| `description` | no | Texto libre |

### `[match]`: cómo se reconoce el juego

Hace falta al menos una condición, y **todas** deben cumplirse. Solo se buscan perfiles para juegos con el motor detectado. Si encajan varios, gana el que tiene más condiciones; a igualdad, uno tuyo gana a uno integrado.

| Campo | Descripción |
|---|---|
| `engine` | Motor detectado, p. ej. `rpgmaker_xp` |
| `runtimes` | Runtimes admitidos: `mkxp-z`, `mkxp`, `rgss1` |
| `titles` | Valores de `Title=` en `Game.ini` (sin distinguir mayúsculas) |
| `files` | Ficheros que deben existir, relativos a la carpeta del juego |

### `[wine]`

| Campo | Descripción |
|---|---|
| `arch` | `win64` (por defecto) o `win32`. `run --arch` tiene prioridad |
| `[wine.environment]` | Variables de entorno para el juego |

Solo se admiten estos nombres exactos, que no cargan código ni rompen el aislamiento del prefijo:

| Grupo | Variables | Valor |
|---|---|---|
| Idioma | `LANG`, `LANGUAGE`, `LC_ALL`, `LC_CTYPE`, `LC_MESSAGES`, `LC_NUMERIC`, `LC_TIME`, `LC_COLLATE`, `LC_MONETARY` | Nombre de locale (`es_ES.UTF-8`), sin `/` |
| Zona horaria | `TZ` | `Europe/Madrid`; nunca una ruta absoluta ni `..` |
| SDL | `SDL_AUDIODRIVER`, `SDL_VIDEODRIVER`, `SDL_RENDER_DRIVER`, `SDL_RENDER_VSYNC` | Opción simple, sin `/` |
| OpenGL | `MESA_GL_VERSION_OVERRIDE`, `MESA_GLSL_VERSION_OVERRIDE`, `MESA_NO_ERROR`, `mesa_glthread`, `LIBGL_ALWAYS_SOFTWARE`, `LIBGL_DRI3_DISABLE`, `__GL_SYNC_TO_VBLANK`, `__GL_THREADED_OPTIMIZATIONS`, `vblank_mode` | Opción simple, sin `/` |
| Audio | `PULSE_LATENCY_MSEC` | Opción simple |

No se admiten prefijos como `LIBGL_*`, `MESA_*` o `SDL_*`: incluyen variables que cargan una biblioteca de cualquier carpeta (`LIBGL_DRIVERS_PATH`, `MESA_LOADER_DRIVER_OVERRIDE`, `SDL_DYNAMIC_API`). Cualquier otra variable (`LD_PRELOAD`, `PATH`, `WINE*`…) es un error. Los valores tienen como máximo 256 caracteres.

### `[saves]`

| Campo | Descripción |
|---|---|
| `paths` | Carpetas donde el juego guarda las partidas |
| `config` | Carpetas de configuración (p. ej. las teclas de mkxp-z) |

Cada ruta empieza por una carpeta conocida y no puede salir de ella con `..`:

| Prefijo | Ruta real |
|---|---|
| `%USERPROFILE%` | `<prefijo>/drive_c/users/<usuario>` |
| `%APPDATA%` | `…/<usuario>/AppData/Roaming` |
| `%LOCALAPPDATA%` | `…/<usuario>/AppData/Local` |
| `%GAMEDIR%` | La carpeta del juego |

> Con Wine, `%USERPROFILE%`, `%APPDATA%` y `%LOCALAPPDATA%` están **dentro del prefijo del juego**. Si se borra el prefijo, se borran las partidas. `run` muestra dónde están.

### `[compatibility]`

| Campo | Descripción |
|---|---|
| `status` | `not_tested`, `not_working`, `partial` o `compatible` (como en [compatibility.md](compatibility.md)) |
| `notes` | Resumen de lo probado |

### `[[known_issues]]`

Problemas conocidos. `check` los lista todos. Los que tienen `output` se reconocen además en la salida del juego, y `run` los explica al terminar.

| Campo | Obligatorio | Descripción |
|---|---|---|
| `id` | sí | Identificador único dentro del perfil |
| `symptom` | sí | Qué ve el jugador |
| `solution` | sí | Qué hacer |
| `output` | no | Textos literales (no expresiones regulares) que delatan el problema en la salida |
| `harmless` | no | `true` si es un mensaje esperado que no afecta al juego. Requiere `output` |

Los problemas del perfil se buscan antes que los generales (OpenGL, wine32, DLL que falta, audio, sesión gráfica). Así, `harmless` sirve para silenciar un aviso general que en ese juego no importa: en Pokémon Z, las DLL que le faltan a `fluidsynth.dll`.
