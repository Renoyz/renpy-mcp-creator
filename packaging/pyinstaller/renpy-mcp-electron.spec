# -*- mode: python ; coding: utf-8 -*-
# ruff: noqa: F821, UP009
from pathlib import Path

repo_root = Path.cwd()
dashboard_dist = repo_root / "dashboard" / "dist"

a = Analysis(
    [str(repo_root / "packaging" / "pyinstaller" / "electron_backend_entry.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[
        (str(dashboard_dist), "dashboard/dist"),
        (str(repo_root / "src" / "renpy_mcp" / "web" / "static"), "renpy_mcp/web/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
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
    name="renpy-mcp-electron",
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
    name="renpy-mcp-electron",
)
