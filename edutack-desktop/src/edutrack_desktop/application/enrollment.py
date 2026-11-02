from dataclasses import dataclass
from typing import Any

from .ports import RecordServicePort, WorkspaceStore


@dataclass(frozen=True)
class PersistedEnrollmentCreation:
    student_id: str
    enrollment_id: str
    student_created: bool


class CreateEnrollmentUseCase:
    """Crea el estudiante opcional y su matrícula mediante una operación SQL atómica."""

    def __init__(self, record_service: RecordServicePort):
        self._record_service = record_service

    async def execute_and_persist(
        self,
        store: WorkspaceStore,
        student_fields: dict[str, Any],
        enrollment_fields: dict[str, Any],
    ) -> PersistedEnrollmentCreation:
        if not isinstance(student_fields, dict) or not isinstance(
            enrollment_fields, dict
        ):
            raise ValueError("Los datos de la matrícula no tienen un formato válido.")

        result = await store.create_enrollment(
            student_fields,
            enrollment_fields,
            self._record_service,
        )
        return PersistedEnrollmentCreation(
            student_id=result["student_id"],
            enrollment_id=result["enrollment_id"],
            student_created=result["student_created"],
        )
