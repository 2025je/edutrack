from collections.abc import Callable
from collections.abc import Coroutine
from inspect import isawaitable
from math import ceil
from typing import Any

from PySide6.QtCore import (
    QByteArray,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    QPersistentModelIndex,
    QThreadPool,
    Qt,
    Signal,
    Slot,
)
from sqlalchemy.exc import SQLAlchemyError

from edutrack_desktop.application.presenters import course_week_groups
from .async_query import AsyncQueryWorker

Row = dict[str, Any]
RowsProvider = Callable[[], list[Row]]
PageResult = tuple[list[Row], int, int]
PageOperation = PageResult | Coroutine[Any, Any, PageResult]
StudentPageProvider = Callable[
    [str, int, int, int, int],
    PageOperation | None,
]
CoursePageProvider = Callable[
    [str, int, int],
    PageOperation | None,
]
EnrollmentPageProvider = Callable[
    [str, int, int, int, int],
    PageOperation | None,
]


class PagedListModel(QAbstractListModel):
    stateChanged = Signal()
    queryFailed = Signal(str, str)

    def __init__(
        self,
        rows_provider: RowsProvider | None,
        roles: dict[str, str],
        page_size: int = 50,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._rows_provider = rows_provider
        self._roles = {
            int(Qt.ItemDataRole.UserRole) + index: (
                role_name,
                source_key,
            )
            for index, (role_name, source_key) in enumerate(roles.items(), start=1)
        }
        self._page_size = page_size
        self._page_index = 0
        self._total_count = 0
        self._matching_count = 0
        self._page_count = 1
        self._visible_rows: list[Row] = []
        self._loaded = False
        self._stale = True
        self._is_loading = False

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._visible_rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or index.row() < 0 or index.column() != 0:
            return None
        role_info = self._roles.get(int(role))
        if role_info is None or index.row() >= len(self._visible_rows):
            return None
        _, source_key = role_info
        return self._visible_rows[index.row()].get(source_key)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            role_id: QByteArray(role_name.encode("utf-8"))
            for role_id, (role_name, _) in self._roles.items()
        }

    @Property(int, notify=stateChanged)
    def totalCount(self) -> int:
        return self._total_count

    @Property(int, notify=stateChanged)
    def matchingCount(self) -> int:
        return self._matching_count

    @Property(int, notify=stateChanged)
    def pageIndex(self) -> int:
        return self._page_index

    @Property(int, notify=stateChanged)
    def pageCount(self) -> int:
        return self._page_count

    @Property(int, constant=True)
    def pageSize(self) -> int:
        return self._page_size

    @Property(bool, notify=stateChanged)
    def isLoading(self) -> bool:
        return self._is_loading

    @Slot(int)
    def setPageIndex(self, page_index: int) -> None:
        page_index = max(0, min(page_index, self._page_count - 1))
        if page_index == self._page_index:
            return
        self._page_index = page_index
        if self._loaded:
            self.refresh()

    @Slot()
    def activate(self) -> None:
        if (not self._loaded or self._stale) and not self._is_loading:
            self.refresh()

    @Slot()
    def refreshIfLoaded(self) -> None:
        if self._loaded or self._is_loading:
            self.refresh()
        else:
            self._stale = True

    @Slot()
    def refresh(self) -> None:
        if self._rows_provider is None:
            return
        rows = self._rows_provider()
        filtered_rows = self._filter_rows(rows)
        self._replace_page(
            filtered_rows,
            len(rows),
            len(filtered_rows),
        )

    def _replace_page(
        self,
        rows: list[Row],
        total_count: int,
        matching_count: int,
        *,
        already_paged: bool = False,
    ) -> None:
        page_count = max(1, ceil(matching_count / self._page_size))
        page_index = min(self._page_index, page_count - 1)
        start = page_index * self._page_size
        self.beginResetModel()
        self._visible_rows = (
            rows[: self._page_size]
            if already_paged
            else rows[start : start + self._page_size]
        )
        self._total_count = total_count
        self._matching_count = matching_count
        self._page_count = page_count
        self._page_index = page_index
        self._loaded = True
        self._stale = False
        self._is_loading = False
        self.endResetModel()
        self.stateChanged.emit()

    def _filter_rows(self, rows: list[Row]) -> list[Row]:
        return rows

    def row_at(self, index: int) -> Row:
        if index < 0 or index >= len(self._visible_rows):
            return {}
        return dict(self._visible_rows[index])


class AsyncPagedListModel(PagedListModel):
    def __init__(
        self,
        roles: dict[str, str],
        page_size: int = 50,
        parent: QObject | None = None,
        query_pool: QThreadPool | None = None,
    ):
        super().__init__(None, roles, page_size, parent)
        self._query_pool = query_pool if query_pool is not None else QThreadPool(self)
        self._query_workers: dict[int, AsyncQueryWorker] = {}
        self._request_id = 0

    def _fetch_page(self) -> PageOperation | None:
        raise NotImplementedError

    def _transform_page_rows(self, rows: list[Row]) -> list[Row]:
        return rows

    @Slot()
    def refresh(self) -> None:
        self._request_id += 1
        request_id = self._request_id
        try:
            page = self._fetch_page()
        except (
            OSError,
            RuntimeError,
            SQLAlchemyError,
            ValueError,
            TypeError,
            KeyError,
        ) as error:
            self._apply_page_error(request_id, type(error).__name__, str(error))
            return
        if page is None:
            self._apply_page_error(
                request_id,
                "MissingPageResult",
                "La consulta no devolvió resultados de página.",
            )
            return
        if isawaitable(page):
            worker = AsyncQueryWorker(request_id, page)
            worker.signals.finished.connect(self._receive_page)
            self._query_workers[request_id] = worker
            self._is_loading = True
            self.stateChanged.emit()
            self._query_pool.start(worker)
            return
        self._apply_page(request_id, page)

    @Slot(int, object, str, str)
    def _receive_page(
        self,
        request_id: int,
        page: object,
        error_type: str,
        error_message: str,
    ) -> None:
        self._query_workers.pop(request_id, None)
        if request_id != self._request_id:
            return
        if error_type:
            self._apply_page_error(request_id, error_type, error_message)
            return
        if not isinstance(page, tuple) or len(page) != 3:
            self._apply_page_error(
                request_id,
                "InvalidPageResult",
                "La consulta devolvió una página de datos no válida.",
            )
            return
        rows, total_count, matching_count = page
        if (
            not isinstance(rows, list)
            or not isinstance(total_count, int)
            or not isinstance(matching_count, int)
        ):
            self._apply_page_error(
                request_id,
                "InvalidPageResult",
                "La consulta devolvió una página de datos no válida.",
            )
            return
        self._apply_page(request_id, (rows, total_count, matching_count))

    def _apply_page_error(
        self,
        request_id: int,
        error_type: str,
        error_message: str,
    ) -> None:
        if request_id != self._request_id:
            return
        self._is_loading = False
        self._stale = True
        self.queryFailed.emit(error_type, error_message)
        self.stateChanged.emit()

    def _apply_page(self, request_id: int, page: PageResult) -> None:
        if request_id != self._request_id:
            return
        rows, total_count, matching_count = page
        page_count = max(1, ceil(matching_count / self._page_size))
        page_index = min(self._page_index, page_count - 1)
        if page_index != self._page_index:
            self._page_index = page_index
            self.refresh()
            return
        self._replace_page(
            self._transform_page_rows(rows),
            total_count,
            matching_count,
            already_paged=True,
        )


class StudentListModel(AsyncPagedListModel):
    def __init__(
        self,
        page_provider: StudentPageProvider,
        page_size: int = 50,
        parent: QObject | None = None,
        query_pool: QThreadPool | None = None,
    ):
        self._page_provider = page_provider
        self._query = ""
        self._status_filter_index = 0
        self._course_filter_id = 0
        super().__init__(
            {
                "studentId": "id",
                "label": "label",
                "courses": "courses",
                "active": "active",
            },
            page_size,
            parent,
            query_pool,
        )

    def _fetch_page(self) -> PageOperation | None:
        return self._page_provider(
            self._query,
            self._status_filter_index,
            self._course_filter_id,
            self._page_index,
            self._page_size,
        )

    @Slot(str, int, int)
    def setFilters(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
    ) -> None:
        query = query.strip()
        status_filter_index = max(0, min(status_filter_index, 2))
        course_filter_id = max(0, course_filter_id)
        if (
            query == self._query
            and status_filter_index == self._status_filter_index
            and course_filter_id == self._course_filter_id
        ):
            self.activate()
            return
        self._query = query
        self._status_filter_index = status_filter_index
        self._course_filter_id = course_filter_id
        self._page_index = 0
        if self._loaded or self._is_loading:
            self.refresh()

    @Slot(str)
    def setQuery(self, query: str) -> None:
        self.setFilters(
            query,
            self._status_filter_index,
            self._course_filter_id,
        )

    @Slot(int, result="QVariantMap")
    def rowAt(self, index: int) -> Row:
        return self.row_at(index)


class CourseListModel(AsyncPagedListModel):
    def __init__(
        self,
        page_provider: CoursePageProvider,
        page_size: int = 50,
        parent: QObject | None = None,
        query_pool: QThreadPool | None = None,
    ):
        self._page_provider = page_provider
        self._query = ""
        super().__init__(
            {
                "weekLabel": "label",
                "courses": "courses",
            },
            page_size,
            parent,
            query_pool,
        )

    def _fetch_page(self) -> PageOperation | None:
        return self._page_provider(
            self._query,
            self._page_index,
            self._page_size,
        )

    def _transform_page_rows(self, rows: list[Row]) -> list[Row]:
        return course_week_groups(rows)

    @Slot(str)
    def setQuery(self, query: str) -> None:
        query = query.strip()
        if query == self._query:
            self.activate()
            return
        self._query = query
        self._page_index = 0
        if self._loaded or self._is_loading:
            self.refresh()

    @Slot(int, result="QVariantMap")
    def rowAt(self, index: int) -> Row:
        return self.row_at(index)


class EnrollmentListModel(AsyncPagedListModel):
    def __init__(
        self,
        page_provider: EnrollmentPageProvider,
        page_size: int = 50,
        parent: QObject | None = None,
        query_pool: QThreadPool | None = None,
    ):
        self._search_query = ""
        self._status_filter_index = 0
        self._course_filter_id = 0
        self._page_provider = page_provider
        super().__init__(
            {
                "enrollmentId": "id",
                "studentLabel": "student_label",
                "courseLabel": "course_label",
                "enrollmentDate": "enrollment_date",
                "pendingStudent": "pending_student",
                "pendingCourse": "pending_course",
                "active": "active",
            },
            page_size,
            parent,
            query_pool,
        )

    def _fetch_page(self) -> PageOperation | None:
        return self._page_provider(
            self._search_query,
            self._status_filter_index,
            self._course_filter_id,
            self._page_index,
            self._page_size,
        )

    @Slot(str, int, int)
    def setFilters(
        self,
        search_query: str,
        status_filter_index: int,
        course_filter_id: int,
    ) -> None:
        search_query = search_query.strip()
        status_filter_index = max(0, min(status_filter_index, 4))
        course_filter_id = max(0, course_filter_id)
        if (
            search_query == self._search_query
            and status_filter_index == self._status_filter_index
            and course_filter_id == self._course_filter_id
        ):
            return
        self._search_query = search_query
        self._status_filter_index = status_filter_index
        self._course_filter_id = course_filter_id
        self._page_index = 0
        if self._loaded or self._is_loading:
            self.refresh()

    @Slot(int, result="QVariantMap")
    def rowAt(self, index: int) -> Row:
        return self.row_at(index)
