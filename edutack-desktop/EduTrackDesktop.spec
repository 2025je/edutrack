from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH)
qt_datas, qt_binaries, qt_hiddenimports = collect_all("PySide6")
datas = qt_datas + [
    (str(ROOT / "edutrack_desktop" / "Main.qml"), "edutrack_desktop"),
    (
        str(ROOT / "edutrack_desktop" / "fonts" / "Roboto[wdth,wght].ttf"),
        "edutrack_desktop/fonts",
    ),
    (
        str(ROOT / "edutrack_desktop" / "fonts" / "OFL.txt"),
        "edutrack_desktop/fonts",
    ),
    (
        str(ROOT / "edutrack_desktop" / "components" / "AppTheme.qml"),
        "edutrack_desktop/components",
    ),
    (
        str(ROOT / "edutrack_desktop" / "components" / "CourseWizardDialog.qml"),
        "edutrack_desktop/components",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "students.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "enrollments.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "courses.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "logo.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "folder-open.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "moon.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "sun.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "export.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "icons" / "add.svg"),
        "edutrack_desktop/icons",
    ),
    (
        str(ROOT / "edutrack_desktop" / "components" / "StudentWizardDialog.qml"),
        "edutrack_desktop/components",
    ),
    (
        str(ROOT / "edutrack_desktop" / "components" / "EnrollmentWizardDialog.qml"),
        "edutrack_desktop/components",
    ),
    (str(ROOT / "edutrack_desktop" / "alembic.ini"), "edutrack_desktop"),
    (
        str(ROOT / "edutrack_desktop" / "migrations" / "env.py"),
        "edutrack_desktop/migrations",
    ),
    (
        str(
            ROOT
            / "edutrack_desktop"
            / "migrations"
            / "versions"
            / "0001_local_workspace.py"
        ),
        "edutrack_desktop/migrations/versions",
    ),
    (
        str(
            ROOT
            / "edutrack_desktop"
            / "migrations"
            / "versions"
            / "0002_initial_campus.py"
        ),
        "edutrack_desktop/migrations/versions",
    ),
]

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
