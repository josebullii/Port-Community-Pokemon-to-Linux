# Matriz de compatibilidad

**Que un juego arranque no basta para declararlo compatible.** Cada prueba debe recorrer la lista de funciones de abajo y anotar el entorno exacto en el que se hizo.

## Estados

| Estado | Significado |
|---|---|
| ⬜ No probado | Todavía no hay ninguna prueba registrada |
| 🟥 No funciona | No arranca o falla al poco de empezar |
| 🟧 Parcial | Se puede jugar, pero hay fallos conocidos (se indican en notas) |
| 🟩 Compatible | Pasa todas las funciones de la lista |

## Funciones que hay que probar

1. Inicio y pantalla de título
2. Menús y opciones
3. Exploración del mapa
4. Combate, con sprites animados activados y desactivados
5. Audio (BGM, efectos y cries)
6. Guardar partida
7. Cargar partida
8. Estabilidad: al menos 30 minutos sin cierres

## Resultados

| Juego | Versión | Motor / runtime | Vía | Distro | Arquitectura | Wine / mkxp-z | Prefijo | Estado | Fecha | Notas |
|---|---|---|---|---|---|---|---|---|---|---|
| Pokémon Z | 2.19 | RPG Maker XP · mkxp-z (SDL2 2.0.12) | Wine | — | x86_64 | — | — | ⬜ | — | Sprint 4 |
| Pokémon Z | 2.19 | RPG Maker XP · mkxp-z | mkxp-z nativo | ArkOS (R36S) | aarch64 | — | n/a | ⬜ | — | Después del MVP |

## Entornos Wine probados (programa de prueba)

Resultado de ejecutar el programa de prueba (`test_program.py`), que debe terminar con código 42:

| Distro | Wine | Paquetes | Prefijo | 64 bits | 32 bits |
|---|---|---|---|---|---|
| Ubuntu 24.04 | 9.0 (Ubuntu 9.0~repack-4build3) | `wine64` solo | win64 | ✅ | ❌ `syswow64\ntdll.dll` no encontrado |
| Ubuntu 24.04 | 9.0 (Ubuntu 9.0~repack-4build3) | `wine wine64 wine32:i386` | win64 | ✅ | ✅ |
| Ubuntu 24.04 | 9.0 (Ubuntu 9.0~repack-4build3) | `wine wine64 wine32:i386` | win32 | ❌ (esperado) | ✅ |

Por tanto, **con Pokémon Z (i386) hace falta `wine32:i386` en Debian/Ubuntu**. Se comprueba con `pokemon-to-linux-cli wine --probe`.

## Ficha de Pokémon Z v2.19

### Diagnóstico automático (sprint 2)

```
$ pokemon-to-linux-cli analyze "POKEMON Z V2.19"
Pokémon to Linux · diagnóstico

  Carpeta:     …/POKEMON Z V2.19
  Título:      Pokemon Z
  Motor:       RPG Maker XP (detectado, confianza 100%)
  Runtime:     mkxp-z (SDL2 2.0.12)
  RGSS:        RGSS104E.dll (versión 1.04, i386)
  Ejecutable:  Game.exe (i386, 32 bits, gui)
  OpenGL:      sí
  DLL:         16 de sistema, 0 incluidas, 0 redistribuibles, 0 faltan
  Ficheros:    19.070 (873,5 MB)

  Indicios:
    +0.10  Game.ini con sección [Game]
    +0.25  Library=RGSS104E.dll (RGSS1)
    +0.15  Scripts=Data\Scripts.rxdata
    +0.15  RGSS102E.dll, RGSS102J.dll, RGSS104E.dll
    +0.25  526 ficheros .rxdata en Data/
    +0.05  carpetas Graphics/ y Audio/
    +0.05  Game.exe (i386, 32 bits)
    +0.00  Game.exe es mkxp-z

  Advertencias:
    (ninguna)
```

Mismo resultado en Windows 11 y en Ubuntu 24.04. La prueba `tests/integration/test_real_games.py` lo verifica cuando se define `PTL_POKEMON_Z_PATH`.

**Qué significa para el sprint 3 (Wine):**
- **El ejecutable es de 32 bits (i386).** El prefijo Wine tiene que poder ejecutar binarios win32, sea un prefijo win32 o uno WoW64.
- **`Game.exe` importa `OPENGL32.DLL`.** El sistema necesita OpenGL funcional, también en 32 bits si Wine no usa WoW64.
- **SDL2 va enlazado dentro de `Game.exe`.** No hay que buscar `SDL2.dll`.
- **Las 16 DLL que importa `Game.exe` son de sistema** (Wine las implementa todas). No hace falta ningún redistribuible.
- **Las DLL RGSS (1.02 E/J y 1.04 E) son i386 válidas**, aunque mkxp-z no las carga.
- **No hace falta ningún RTP** (`RTP1`, `RTP2` y `RTP3` están vacíos).

### Contenido de la carpeta

Datos obtenidos al analizar los archivos del juego:

- `Game.ini`: `Library=RGSS104E.dll`, `Scripts=Data\Scripts.rxdata`, `Title=Pokemon Z`
- `Game.exe`: mkxp-z (PE32 i386, interfaz gráfica). Importa 16 DLL de sistema, entre ellas `OPENGL32.DLL`. Hay una copia idéntica en `Data/Game.exe`.
- DLL presentes: `RGSS102E.dll`, `RGSS102J.dll`, `RGSS104E.dll`, `fluidsynth.dll`, `gif.dll`, `KleinBitmap.dll`, `rgssdisp.dll`, `rubyscreen.dll`
- Configuración de mkxp-z: `mkxp.json` (`vsync: false`, `enableBlitting: true`…) y `preload.rb` (parche de Zlib)
- `Editor.ini` apunta a `RGSS102E.dll` y `EditorScripts.rxdata`, el editor de Pokémon Essentials. No es el juego.
- Fuentes propias en `Fonts/` (8 TTF)
- Tamaño: unos 915 MB

### Problemas conocidos en PC

Según la documentación del propio juego:

| Síntoma | Solución |
|---|---|
| El juego va demasiado rápido | Desactivar VSync en las opciones del juego |
| Pantalla negra en pantalla completa | Activar FXAA en el driver gráfico |
| Se cierra al sacar un Pokémon | Desactivar los sprites animados |
| Error de OpenGL o barras verdes | Actualizar los drivers. Si no se arregla, la GPU es incompatible |
| `NameError` en Random | Configuración regional que no es española. En Wine, probar con `LANG=es_ES.UTF-8` |
