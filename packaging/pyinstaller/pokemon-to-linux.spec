# -*- mode: python ; coding: utf-8 -*-
# Ejecutable único para Linux x86_64. Se construye desde la raíz del repositorio:
#
#   pip install . pyinstaller
#   pyinstaller --noconfirm packaging/pyinstaller/pokemon-to-linux.spec
#
# El resultado queda en dist/pokemon-to-linux. Ver docs/development.md.
import os

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = []
datas += collect_data_files("pokemon_to_linux")  # perfiles TOML integrados
datas += copy_metadata("pokemon-to-linux")  # para que __version__ sea la real

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],  # noqa: F821 (SPECPATH lo define PyInstaller)
    datas=datas,
    # Módulos de PySide6 que la aplicación no usa y engordan el ejecutable.
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pokemon-to-linux",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,  # la CLI («cli …») escribe en la terminal
)
