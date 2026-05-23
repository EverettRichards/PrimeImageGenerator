# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['C:\\Users\\ehric\\Documents\\PrimeImageGenerator\\windows_ascii_app\\..'],
    binaries=[],
    datas=[('C:\\Users\\ehric\\Documents\\PrimeImageGenerator\\windows_ascii_app\\..\\shared_ascii_app', 'shared_ascii_app')],
    hiddenimports=['shared_ascii_app', 'shared_ascii_app.engine', 'shared_ascii_app.gui'],
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
    name='VADIM_ASCII_Generator',
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
)
