from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH)
SRC_DIR = ROOT / "src"
APP_DIR = SRC_DIR / "edutrack_desktop"
qt_datas, qt_binaries, qt_hiddenimports = collect_all("PySide6")
hiddenimports = qt_hiddenimports + [
    "aiosqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
]
resource_suffixes = {".ini", ".qml", ".svg", ".ttf", ".txt"}
app_datas = []
for path in APP_DIR.rglob("*"):
    if not path.is_file() or "__pycache__" in path.parts:
        continue
    is_migration = (
        path.suffix == ".py"
        and APP_DIR / "infrastructure" / "migrations" in path.parents
    )
    if path.suffix in resource_suffixes or is_migration:
        app_datas.append((str(path), str(path.parent.relative_to(SRC_DIR))))

datas = qt_datas + app_datas

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(SRC_DIR), str(ROOT)],
    binaries=qt_binaries,
    datas=datas,
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
