# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Ensure the Analysis searches the repository root (absolute path) so local
# packages like `shared_ascii_app` are discovered during analysis.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

hiddenimports = []
datas = []
binaries = []

for package_name in ["PIL", "reportlab", "numpy"]:
    collected = collect_all(package_name)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

# Explicitly include the local package modules that static analysis can
# sometimes miss when imports are performed dynamically or when sys.path is
# altered during runtime. This ensures `shared_ascii_app` is bundled.
hiddenimports += [
    "shared_ascii_app",
    "shared_ascii_app.engine",
    "shared_ascii_app.gui",
]

# Ensure all submodules of the local package are included as importable modules
try:
    hiddenimports += collect_submodules("shared_ascii_app")
except Exception:
    # If collect_submodules fails for any reason, fall back to explicit names above
    pass


a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VADIM_ASCII_Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VADIM_ASCII_Generator",
)
