import sys
from pathlib import Path

from nox import Session, options
from nox_uv import session

options.default_venv_backend = "uv"
options.sessions = ["qml_lint", "coverage", "lint", "typecheck"]


@session(uv_groups=["test"])
def tests(session: Session) -> None:
    session.run("pytest", *session.posargs)


@session(uv_groups=["test", "coverage"])
def coverage(session: Session) -> None:
    session.run(
        "pytest",
        "--cov=edutrack_desktop",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=xml",
        *session.posargs,
    )


@session(uv_only_groups=["lint"])
def lint(session: Session) -> None:
    session.run("ruff", "check", ".", *session.posargs)


@session(uv_groups=["typecheck"])
def typecheck(session: Session) -> None:
    session.run("mypy", *session.posargs)


@session(uv_groups=["test"])
def qml_lint(session: Session) -> None:
    qml_root = Path(__file__).parent / "src" / "edutrack_desktop" / "presentation" / "qml"
    qml_files = sorted(qml_root.rglob("*.qml"))
    if not qml_files:
        raise RuntimeError(f"No QML files found under {qml_root}")
    session.run("pyside6-qmllint", *(str(path) for path in qml_files), *session.posargs)


@session(uv_groups=["test"])
def performance(session: Session) -> None:
    session.run(
        "pytest",
        "-m",
        "performance",
        "--benchmark-only",
        "-q",
        *session.posargs,
    )


@session(uv_groups=["dev"])
def build(session: Session) -> None:
    if sys.platform != "win32":
        raise RuntimeError("The EduTrack Desktop build is available only on Windows.")

    build_script = Path(__file__).parent / "build.ps1"
    session.run(
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(build_script),
        *session.posargs,
        external=True,
    )
