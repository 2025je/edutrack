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
    console_output = sys.stderr is not None
    if console_output:
        colorama.just_fix_windows_console()

    if not root_logger.handlers:
        if not console_output:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        else:
            handler = RichHandler(
                console=Console(stderr=True),
                rich_tracebacks=True,
                show_path=False,
            )
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
