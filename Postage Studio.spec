# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['postage_app.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/postage-studio.ico','assets'), ('LICENSE','.'), ('THIRD_PARTY_NOTICES.md','.'), ('licenses','licenses')],
    hiddenimports=['winrt.windows.foundation', 'winrt.windows.foundation.collections',
                   'winrt.windows.globalization', 'winrt.windows.graphics.imaging',
                   'winrt.windows.media.ocr', 'winrt.windows.storage.streams'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQml', 'PySide6.QtQuick', 'pandas', 'scipy', 'matplotlib', 'IPython', 'pytest'],
    noarchive=False,
    optimize=0,
)
# Qt 6.12 uses the unversioned ICU API supplied by Windows 10/11.
# An unrelated ICU from PATH exports version-suffixed symbols and breaks QtCore.
# Let Windows resolve its own ICU libraries instead of bundling PATH copies.
a.binaries = [entry for entry in a.binaries
              if entry[0].replace('\\', '/').split('/')[-1].lower()
              not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='Postage Studio',
    icon='assets/postage-studio.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
