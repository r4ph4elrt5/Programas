# PyInstaller onedir. Build on the target operating system.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ctk_datas, ctk_binaries, ctk_imports = collect_all('customtkinter')
# Some standalone Python distributions keep Tcl/Tk shared libraries alongside
# Python rather than in the loader's default system paths. Include the actual
# runtime libraries on Linux; Windows continues to use PyInstaller's Tk hooks.
runtime_binaries = []
if sys.platform.startswith('linux'):
    runtime_lib = Path(sys.base_prefix) / 'lib'
    runtime_binaries = [
        (str(library), '.')
        for pattern in ('libtcl*.so', 'libtk*.so')
        for library in sorted(runtime_lib.glob(pattern))
        if library.is_file()
    ]
hiddenimports = ctk_imports + collect_submodules('googleapiclient')
hiddenimports += collect_submodules('google_auth_oauthlib')
hiddenimports += collect_submodules('keyring.backends')
hiddenimports += collect_submodules('uvicorn')

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=ctk_binaries + runtime_binaries,
    datas=ctk_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MultiPost',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='MultiPost',
)
