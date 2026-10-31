from collections.abc import Callable
from math import ceil
from typing import Any

from PySide6.QtCore import (
    QByteArray,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from edutrack_desktop.application.presenters import course_week_groups

Row = dict[str, Any]
RowsProvider = Callable[[], list[Row]]
StudentPageProvider = Callable[
    [str, int, int, int, int],
    tuple[list[Row], int, int] | None,
]
CoursePageProvider = Callable[
    [str, int, int],
    tuple[list[Row], int, int] | None,
]


class PagedListModel(QAbstractListModel):
    stateChanged = Signal()

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
        if not self._loaded or self._stale:
            self.refresh()

    @Slot()
    def refreshIfLoaded(self) -> None:
        if self._loaded:
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
        self.endResetModel()
        self.stateChanged.emit()

    def _filter_rows(self, rows: list[Row]) -> list[Row]:
        return rows

    def row_at(self, index: int) -> Row:
        if index < 0 or index >= len(self._visible_rows):
            return {}
        return dict(self._visible_rows[index])


class StudentListModel(PagedListModel):
    def __init__(
        self,
        page_provider: StudentPageProvider,
        page_size: int = 50,
        parent: QObject | None = None,
    ):
        self._page_provider = page_provider
        self._query = ""
        self._status_filter_index = 0
        self._course_filter_id = 0
        super().__init__(
            None,
            {
                "studentId": "id",
                "label": "label",
                "courses": "courses",
                "active": "active",
            },
            page_size,
            parent,
        )

    def refresh(self) -> None:
        page = self._page_provider(
            self._query,
            self._status_filter_index,
            self._course_filter_id,
            self._page_index,
            self._page_size,
        )
        if page is None:
            return
        rows, total_count, matching_count = page
        page_count = max(1, ceil(matching_count / self._page_size))
        page_index = min(self._page_index, page_count - 1)
        if page_index != self._page_index:
            self._page_index = page_index
            page = self._page_provider(
                self._query,
                self._status_filter_index,
                self._course_filter_id,
                self._page_index,
                self._page_size,
            )
            if page is None:
                return
            rows, total_count, matching_count = page
        self._replace_page(
            rows,
            total_count,
            matching_count,
            already_paged=True,
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
        if self._loaded:
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


class CourseListModel(PagedListModel):
    def __init__(
        self,
        page_provider: CoursePageProvider,
        page_size: int = 50,
        parent: QObject | None = None,
    ):
        self._page_provider = page_provider
        self._query = ""
        super().__init__(
            None,
            {
                "weekLabel": "label",
                "courses": "courses",
            },
            page_size,
            parent,
        )

    def refresh(self) -> None:
        page = self._page_provider(
            self._query,
            self._page_index,
            self._page_size,
        )
        if page is None:
            return
        rows, total_count, matching_count = page
        page_count = max(1, ceil(matching_count / self._page_size))
        page_index = min(self._page_index, page_count - 1)
        if page_index != self._page_index:
            self._page_index = page_index
            page = self._page_provider(
                self._query,
                self._page_index,
                self._page_size,
            )
            if page is None:
                return
            rows, total_count, matching_count = page
        self._replace_page(
            course_week_groups(rows),
            total_count,
            matching_count,
            already_paged=True,
        )

    @Slot(str)
    def setQuery(self, query: str) -> None:
        query = query.strip()
        if query == self._query:
            self.activate()
            return
        self._query = query
        self._page_index = 0
        if self._loaded:
            self.refresh()

    @Slot(int, result="QVariantMap")
    def rowAt(self, index: int) -> Row:
        return self.row_at(index)


class EnrollmentListModel(PagedListModel):
    def __init__(
        self,
        rows_provider: RowsProvider,
        page_size: int = 50,
        parent: QObject | None = None,
    ):
        self._search_query = ""
        self._status_filter_index = 0
        self._course_filter_id = 0
        super().__init__(
            rows_provider,
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
        )

    @Slot(str, int, int)
    def setFilters(
        self,
        search_query: str,
        status_filter_index: int,
        course_filter_id: int,
    ) -> None:
        search_query = search_query.strip().casefold()
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
        if self._loaded:
            self.refresh()

    def _filter_rows(self, rows: list[Row]) -> list[Row]:
        filtered_rows = []
        for row in rows:
            if self._search_query:
                searchable_text = " ".join(
                    (
                        str(row.get("student_label", "")),
                        str(row.get("course_label", "")),
                        str(row.get("enrollment_date", "")),
                    )
                ).casefold()
                if self._search_query not in searchable_text:
                    continue

            if self._course_filter_id and (
                row.get("course_id") != self._course_filter_id
            ):
                continue

            if self._status_filter_index == 1 and not (
                row.get("active", True)
                and not row.get("pending_student", False)
                and not row.get("pending_course", False)
            ):
                continue
            if self._status_filter_index == 2 and row.get("active", True):
                continue
            if self._status_filter_index == 3 and not row.get(
                "pending_student", False
            ):
                continue
            if self._status_filter_index == 4 and not row.get(
                "pending_course", False
            ):
                continue
            filtered_rows.append(row)
        return filtered_rows

    @Slot(int, result="QVariantMap")
    def rowAt(self, index: int) -> Row:
        return self.row_at(index)
