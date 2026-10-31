import asyncio
import sqlite3
from collections.abc import Coroutine
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal
from sqlalchemy.exc import SQLAlchemyError


def run_async_operation(operation: Coroutine[Any, Any, Any]) -> Any:
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(operation)


class AsyncQuerySignals(QObject):
    finished = Signal(int, object, str, str)


class AsyncQueryWorker(QRunnable):
    def __init__(
        self,
        request_id: int,
        operation: Coroutine[Any, Any, Any],
    ):
        super().__init__()
        self.request_id = request_id
        self.operation = operation
        self.signals = AsyncQuerySignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = run_async_operation(self.operation)
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            sqlite3.Error,
            ValueError,
            TypeError,
            KeyError,
        ) as error:
            self.signals.finished.emit(
                self.request_id,
                None,
                type(error).__name__,
                str(error),
            )
        else:
            self.signals.finished.emit(self.request_id, result, "", "")
