import logging

from sqlalchemy import text

from edutrack_desktop.infrastructure.logging_config import configure_logging
from edutrack_desktop.infrastructure.store import LocalStore


def test_sql_statements_are_logged_without_bound_values(caplog, tmp_path):
    log_path = tmp_path / "logs" / "desktop.jsonl"
    configure_logging("DEBUG", log_path)
    store = LocalStore(tmp_path / "workspace.sqlite3")
    private_value = "student-private-value"

    with caplog.at_level(logging.DEBUG):
        with store.engine.connect() as connection:
            connection.execute(
                text("SELECT :private_value"),
                {"private_value": private_value},
            )

    assert "database.statement" in caplog.text
    assert "SELECT ?" in caplog.text
    assert str(store.path) in caplog.text
    assert private_value not in caplog.text
