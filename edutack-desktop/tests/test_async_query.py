import asyncio

from edutrack_desktop.presentation.async_query import AsyncQueryWorker


def test_async_query_worker_uses_selector_event_loop():
    async def current_loop_type():
        return type(asyncio.get_running_loop())

    results = []
    worker = AsyncQueryWorker(1, current_loop_type())
    worker.signals.finished.connect(
        lambda request_id, result, error_type, error_message: results.append(
            (request_id, result, error_type, error_message)
        )
    )

    worker.run()

    assert results == [(1, asyncio.SelectorEventLoop, "", "")]
