from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol


class DatabaseEngine(Protocol):
    def dispose(self) -> None: ...


class WorkspaceStore(Protocol):
    path: Path

    @property
    def engine(self) -> DatabaseEngine: ...

    def load(self) -> dict[str, Any] | None: ...

    def save(self, manifest: dict[str, Any]) -> None: ...


class CampusCatalogPort(Protocol):
    records: list[dict[str, str]]
    active_path: str

    def contains(self, path: str | Path) -> bool: ...

    def register(
        self, path: str | Path, campus_name: str, activate: bool = True
    ) -> None: ...

    def activate(self, path: str | Path) -> None: ...

    def deactivate(self) -> None: ...


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
    ) -> int: ...

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
    ) -> None: ...

    def create_promoter(self, manifest: dict[str, Any], name: str) -> int: ...

    def save_student(
        self,
        manifest: dict[str, Any],
        source_id: str,
        last_name: str,
        first_name: str,
        document_number: str,
        phone_text: str,
    ) -> str: ...

    def save_enrollment(
        self, manifest: dict[str, Any], source_id: str, fields: dict[str, Any]
    ) -> str: ...

    def remove_unused_attachments(self, manifest: dict[str, Any]) -> None: ...


StoreFactory = Callable[[Path], WorkspaceStore]
CampusCatalogFactory = Callable[[Path], CampusCatalogPort]
