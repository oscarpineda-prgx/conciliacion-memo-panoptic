# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Bundle all submodules of our package (lazy imports inside functions are
# not detected by static analysis, so we collect them explicitly).
_hidden = collect_submodules('conciliacion_memo_panoptic')

# customtkinter loads theme JSON / image assets at runtime from its package
# directory — must be included as data files.
_datas = collect_data_files('customtkinter')
_datas += [
    ('src\\conciliacion_memo_panoptic\\assets', 'conciliacion_memo_panoptic\\assets'),
]

a = Analysis(
    ['launch_gui.py'],
    pathex=['src'],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Conciliacion PRGX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src\\conciliacion_memo_panoptic\\assets\\prgx-icon.ico'],
)
