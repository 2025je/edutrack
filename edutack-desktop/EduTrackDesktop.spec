from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH)
APP_DIR = ROOT / "edutrack_desktop"
qt_datas, qt_binaries, qt_hiddenimports = collect_all("PySide6")
resource_suffixes = {".ini", ".qml", ".svg", ".ttf", ".txt"}
app_datas = []
for path in APP_DIR.rglob("*"):
    if not path.is_file() or "__pycache__" in path.parts:
        continue
    is_migration = (
        path.suffix == ".py" and APP_DIR / "migrations" in path.parents
    )
    if path.suffix in resource_suffixes or is_migration:
        app_datas.append((str(path), str(path.parent.relative_to(ROOT))))

datas = qt_datas + app_datas

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=qt_binaries,
    datas=datas,
    hiddenimports=qt_hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name="EduTrackDesktop",
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
