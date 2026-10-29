import logging

import structlog

from edutrack_desktop.infrastructure.logging_config import configure_logging


def test_structlog_emits_readable_console_events(caplog, tmp_path):
    configure_logging("INFO", tmp_path / "logs" / "desktop.jsonl")

    with caplog.at_level(logging.INFO):
        structlog.get_logger("test.desktop").info(
            "desktop.test_event",
            component="backend",
        )

    assert "desktop.test_event" in caplog.text
    assert "component" in caplog.text
    assert '"event":' not in caplog.text
