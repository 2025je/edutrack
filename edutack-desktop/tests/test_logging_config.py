import logging

import structlog

from edutrack_desktop.infrastructure.logging_config import configure_logging


def test_structlog_emits_json_events(caplog, tmp_path):
    configure_logging("INFO", tmp_path / "logs" / "desktop.jsonl")

    with caplog.at_level(logging.INFO):
        structlog.get_logger("test.desktop").info(
            "desktop.test_event",
            component="backend",
        )

    assert '"event": "desktop.test_event"' in caplog.text
    assert '"component": "backend"' in caplog.text
