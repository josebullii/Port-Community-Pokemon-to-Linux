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

## Ficha de Pokémon Z v2.19

Datos obtenidos al analizar los archivos del juego:

- `Game.ini`: `Library=RGSS104E.dll`, `Scripts=Data\Scripts.rxdata`, `Title=Pokemon Z`
- `Game.exe`: mkxp-z (PE32 i386). Hay una copia en `Data/Game.exe`.
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
