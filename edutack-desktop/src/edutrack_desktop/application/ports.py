from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from edutrack_desktop.domain.record_service import RecordMutation


class WorkspaceStore(Protocol):
    path: Path

    async def load(self) -> dict[str, Any] | None: ...

    async def save(self, manifest: dict[str, Any]) -> None: ...

    async def save_with_sync_history(
        self, manifest: dict[str, Any], history_event: dict[str, Any]
    ) -> None: ...

    async def save_records(
        self, manifest: dict[str, Any], changes: dict[str, list[RecordMutation]]
    ) -> None: ...

    async def search_students(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]: ...

    async def student_page(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]: ...

    async def course_page(
        self,
        query: str,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]: ...

    async def enrollment_page(
        self,
        query: str,
        status_filter_index: int,
        course_filter_id: int,
        page_index: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, int]: ...

    async def record_sync_history(self, history_event: dict[str, Any]) -> None: ...

    async def list_sync_history(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def has_imported_bundle(self, bundle_id: str) -> bool: ...

    def create_backup(self, destination: Path) -> Path: ...

    async def dispose(self) -> None: ...


class CampusCatalogPort(Protocol):
    path: Path
    records: list[dict[str, str]]
    active_path: str

    def contains(self, path: str | Path) -> bool: ...

    def register(
        self, path: str | Path, campus_name: str, activate: bool = True
    ) -> None: ...

    def activate(self, path: str | Path) -> None: ...

    def deactivate(self) -> None: ...

    def remove(self, path: str | Path) -> bool: ...


class RecordServicePort(Protocol):
    def create_course(
        self,
        manifest: dict[str, Any],
        name: str,
        schedule: str,
        group_name: str,
        start_date: str,
        enrollment_fee: str,
        monthly_fee: str,
        capacity: str,
    ) -> RecordMutation: ...

    def update_course(
        self,
        manifest: dict[str, Any],
        course_id: int,
        name: str,
        schedule: str,
        group_name: str,
        start_date: str,
        enrollment_fee: str,
        monthly_fee: str,
        capacity: str,
        active: bool,
    ) -> RecordMutation: ...

    def create_promoter(
        self, manifest: dict[str, Any], name: str
    ) -> RecordMutation: ...

    def save_student(
        self,
        manifest: dict[str, Any],
        source_id: str,
        last_name: str,
        first_name: str,
        document_number: str,
        phone_text: str,
    ) -> RecordMutation: ...

    def set_student_active(
        self, manifest: dict[str, Any], student_id: str, active: bool
    ) -> RecordMutation: ...

    def save_enrollment(
        self, manifest: dict[str, Any], source_id: str, fields: dict[str, Any]
    ) -> RecordMutation: ...

    def remove_unused_attachments(self, manifest: dict[str, Any]) -> None: ...


StoreFactory = Callable[[Path], WorkspaceStore]
CampusCatalogFactory = Callable[[Path], CampusCatalogPort]
