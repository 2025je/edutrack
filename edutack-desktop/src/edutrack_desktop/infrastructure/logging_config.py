import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def configure_logging(level: str, log_path: Path) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if sys.stderr is None:
            handler: logging.Handler = RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        else:
            handler = logging.StreamHandler(sys.stderr)
        root_logger.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
