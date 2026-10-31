import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler

from sqlalchemy import text
import structlog

from edutrack_desktop.infrastructure import logging_config
from edutrack_desktop.infrastructure.logging_config import configure_logging
from edutrack_desktop.infrastructure.store import LocalStore


def test_sql_statement_logging_is_disabled(caplog, tmp_path):
    log_path = tmp_path / "logs" / "desktop.jsonl"
    configure_logging("DEBUG", log_path)
    store = LocalStore(tmp_path / "workspace.sqlite3")
    private_value = "student-private-value"

    async def execute_query():
        async with store.engine.connect() as connection:
            await connection.execute(
                text("SELECT :private_value"),
                {"private_value": private_value},
            )

    with caplog.at_level(logging.DEBUG):
        asyncio.run(execute_query())

    assert "database.statement" not in caplog.text
    assert "SELECT ?" not in caplog.text
    assert private_value not in caplog.text


def test_headless_logging_writes_rotating_json_with_existing_handlers(
    monkeypatch, tmp_path
):
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    external_handler = logging.NullHandler()
    root_logger.addHandler(external_handler)
    log_path = tmp_path / "logs" / "desktop.jsonl"
    monkeypatch.setattr(logging_config.sys, "stderr", None)

    try:
        configure_logging("INFO", log_path)
        file_handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        handler = file_handlers[0]
        assert handler.maxBytes == 1_000_000
        assert handler.backupCount == 3

        structlog.get_logger("edutrack_desktop.tests.diagnostics").info(
            "database.records_saved",
            student_count=4,
            enrollment_count=2,
        )
        handler.flush()

        event = json.loads(log_path.read_text(encoding="utf-8"))
        assert event["event"] == "database.records_saved"
        assert event["student_count"] == 4
        assert event["enrollment_count"] == 2
        assert event["level"] == "info"

        handler.maxBytes = 100
        structlog.get_logger("edutrack_desktop.tests.diagnostics").info(
            "rotation.trigger",
            padding="x" * 200,
        )
        handler.flush()
        assert (log_path.parent / "desktop.jsonl.1").is_file()
    finally:
        for handler in tuple(root_logger.handlers):
            if getattr(handler, "_edutrack_desktop_managed", False):
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.removeHandler(external_handler)
        root_logger.setLevel(previous_level)


def test_validation_rejection_logs_no_user_input(monkeypatch, tmp_path):
    from edutrack_desktop.presentation.backend import DesktopBackend

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    log_path = tmp_path / "logs" / "desktop.jsonl"
    monkeypatch.setattr(logging_config.sys, "stderr", None)

    try:
        configure_logging("WARNING", log_path)
        DesktopBackend._log_validation_failure(
            "student.save",
            ValueError("Documento privado 12345678"),
        )
        for handler in root_logger.handlers:
            if getattr(handler, "_edutrack_desktop_managed", False):
                handler.flush()

        log_content = log_path.read_text(encoding="utf-8")
        assert "validation.rejected" in log_content
        assert "student.save" in log_content
        assert "ValueError" in log_content
        assert "Documento privado 12345678" not in log_content
    finally:
        for handler in tuple(root_logger.handlers):
            if getattr(handler, "_edutrack_desktop_managed", False):
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.setLevel(previous_level)
