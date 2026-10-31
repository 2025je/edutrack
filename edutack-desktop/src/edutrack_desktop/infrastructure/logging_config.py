import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama
import structlog
from rich.console import Console
from rich.logging import RichHandler


def configure_logging(level: str, log_path: Path) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("edutrack_desktop.infrastructure.store").setLevel(
        logging.WARNING
    )
    console_output = sys.stderr is not None
    if console_output:
        colorama.just_fix_windows_console()

    for existing_handler in tuple(root_logger.handlers):
        if getattr(existing_handler, "_edutrack_desktop_managed", False):
            root_logger.removeHandler(existing_handler)
            existing_handler.close()

    if not console_output:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        setattr(handler, "_edutrack_desktop_managed", True)
        root_logger.addHandler(handler)
    elif not root_logger.handlers:
        handler = RichHandler(
            console=Console(stderr=True),
            rich_tracebacks=True,
            show_path=False,
        )
        setattr(handler, "_edutrack_desktop_managed", True)
        root_logger.addHandler(handler)

    if console_output:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
