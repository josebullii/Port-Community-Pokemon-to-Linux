"""Punto de entrada del ejecutable: la interfaz, o la CLI con «cli» delante.

    pokemon-to-linux                 → interfaz gráfica
    pokemon-to-linux cli check …     → igual que pokemon-to-linux-cli check …
"""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from pokemon_to_linux.cli import main as cli_main

        sys.argv = ["pokemon-to-linux cli", *sys.argv[2:]]
        sys.exit(cli_main(sys.argv[1:]))
    from pokemon_to_linux.main import main

    sys.exit(main())
