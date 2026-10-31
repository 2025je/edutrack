import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def create_sqlite_backup(source_path: Path, destination_path: Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No se encontró la base de datos: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass

    try:
        source_uri = f"{source.as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
            with closing(sqlite3.connect(destination)) as destination_connection:
                source_connection.backup(destination_connection)
                result = destination_connection.execute("PRAGMA quick_check").fetchone()
                if result is None or result[0] != "ok":
                    raise sqlite3.DatabaseError(
                        "La copia de seguridad no pasó la verificación de SQLite."
                    )
                destination_connection.commit()
    except (OSError, sqlite3.Error):
        destination.unlink(missing_ok=True)
        raise

    return destination


def verify_sqlite_backup(path: Path) -> dict[str, object]:
    backup = Path(path).expanduser().resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"No se encontró el respaldo: {backup}")

    source_uri = f"{backup.as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise sqlite3.DatabaseError(
                "El respaldo no pasó la verificación de integridad de SQLite."
            )

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required_tables = {
            "desktop_workspaces",
            "desktop_students",
            "desktop_enrollments",
            "desktop_courses",
            "desktop_promoters",
        }
        if not required_tables.issubset(tables):
            raise sqlite3.DatabaseError(
                "El archivo no contiene todas las tablas de una sede EduTrack."
            )

        row = connection.execute(
            """
            SELECT format, version, bundle_id, campus_id, campus_name
            FROM desktop_workspaces
            WHERE id = 1
            """
        ).fetchone()
        if row is None or row[0] != "edutrack-offline":
            raise sqlite3.DatabaseError(
                "El respaldo no contiene un espacio de trabajo EduTrack válido."
            )

        foreign_key_error = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchone()
        if foreign_key_error is not None:
            raise sqlite3.DatabaseError(
                "El respaldo contiene relaciones de base de datos inválidas."
            )

    return {
        "format": row[0],
        "version": row[1],
        "bundle_id": row[2],
        "campus_id": row[3],
        "campus_name": row[4],
    }


def restore_sqlite_backup(source_path: Path, destination_path: Path) -> Path:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if source == destination:
        raise ValueError("El respaldo no puede sobrescribir su propio archivo.")

    verify_sqlite_backup(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged_path = destination.with_name(
        f".{destination.name}.{uuid4().hex}.restore"
    )
    try:
        create_sqlite_backup(source, staged_path)
        verify_sqlite_backup(staged_path)
        os.replace(staged_path, destination)
    except (OSError, sqlite3.Error, ValueError):
        staged_path.unlink(missing_ok=True)
        raise

    return destination
