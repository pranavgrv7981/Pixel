# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

block_cipher = None

project_dir = Path(r"E:\AI AGENT").resolve()

added_files = [
    (str(project_dir / ".env.example"), "."),
]

hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "sqlite3",
    "sounddevice",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "faster_whisper",
    "ollama",
    "httpx",
    "pydantic",
    "pydantic_settings",
    "app",
    "app.agent",
    "app.browser",
    "app.context",
    "app.core",
    "app.events",
    "app.knowledge",
    "app.memory",
    "app.models",
    "app.planning",
    "app.security",
    "app.tasks",
    "app.tools",
    "app.ui",
    "app.ui.animation",
    "app.ui.widgets",
    "app.ui.widgets.pixel_core",
    "app.ui.widgets.diagnostics_drawer",
    "app.voice",
]

a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 1. Onedir Mode (Production directory distribution)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # Set console=True for development/logging or False for windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalAssistant",
)
