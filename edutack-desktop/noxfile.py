from nox import Session, options
from nox_uv import session

options.default_venv_backend = "uv"
options.sessions = ["coverage", "lint", "typecheck"]


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
def performance(session: Session) -> None:
    session.run(
        "pytest",
        "-m",
        "performance",
        "--benchmark-only",
        "-q",
        *session.posargs,
    )
