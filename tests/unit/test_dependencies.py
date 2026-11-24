import pytest

from pokemon_to_linux.domain.dependencies import (
    classify_imports,
    is_redistributable_dll,
    is_system_dll,
)

# Importaciones reales de Game.exe (mkxp-z) de Pokémon Z v2.19.
POKEMON_Z_IMPORTS = (
    "advapi32.dll", "gdi32.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll", "msvcrt.dll",
    "ole32.dll", "oleaut32.dll", "opengl32.dll", "setupapi.dll", "shell32.dll", "user32.dll",
    "version.dll", "winmm.dll", "ws2_32.dll", "wsock32.dll",
)  # fmt: skip


def test_pokemon_z_imports_are_all_system():
    report = classify_imports(POKEMON_Z_IMPORTS, bundled_files=["RGSS104E.dll"])

    assert report.system == POKEMON_Z_IMPORTS
    assert report.missing == report.bundled == report.redistributable == ()


@pytest.mark.parametrize(
    "name",
    ["KERNEL32.dll", "opengl32.dll", "winspool.drv", "api-ms-win-crt-runtime-l1-1-0.dll"],
)
def test_system_dlls(name):
    assert is_system_dll(name)


@pytest.mark.parametrize(
    "name",
    [
        "MSVCP140.dll",
        "vcruntime140_1.dll",
        "msvcr100.dll",
        "d3dx9_43.dll",
        "xinput1_3.dll",
        "OpenAL32.dll",
        "d3dcompiler_43.dll",
    ],
)
def test_redistributable_dlls(name):
    assert is_redistributable_dll(name)
    assert not is_system_dll(name)


def test_d3dcompiler_47_is_system():
    assert is_system_dll("d3dcompiler_47.dll")
    assert not is_redistributable_dll("d3dcompiler_47.dll")


def test_classification_order_and_case():
    report = classify_imports(
        ["KERNEL32.dll", "fmod.dll", "MSVCP140.dll", "rare.dll", "opengl32.dll", "kernel32.dll"],
        bundled_files=["FMOD.DLL", "opengl32.dll"],
    )

    assert report.system == ("kernel32.dll",)  # sin duplicados
    # Una copia local gana al sistema, como en el orden de búsqueda de Windows.
    assert report.bundled == ("fmod.dll", "opengl32.dll")
    assert report.redistributable == ("msvcp140.dll",)
    assert report.missing == ("rare.dll",)


def test_to_dict():
    data = classify_imports(["rare.dll"], []).to_dict()

    assert data == {"system": [], "bundled": [], "redistributable": [], "missing": ["rare.dll"]}
