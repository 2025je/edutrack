from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from edutrack_desktop.domain.record_service import RecordMutation

from .ports import RecordServicePort


@dataclass(frozen=True)
class EnrollmentCreation:
    manifest: dict[str, Any]
    student_id: str
    enrollment_id: str
    student_created: bool
    student_change: RecordMutation | None
    enrollment_change: RecordMutation


class CreateEnrollmentUseCase:
    """Crea un estudiante (cuando corresponde) y su matrícula como una sola operación.

    Trabaja sobre una copia del manifiesto: si cualquier validación falla, el
    manifiesto original queda intacto y no se crea un estudiante sin matrícula.
    El guardado físico del manifiesto resultante sigue siendo responsabilidad
    del llamador, en una única transacción de la capa de infraestructura.
    """

    def __init__(self, record_service: RecordServicePort):
        self._record_service = record_service

    def execute(
        self,
        manifest: dict[str, Any] | None,
        student_fields: dict[str, Any],
        enrollment_fields: dict[str, Any],
    ) -> EnrollmentCreation:
        if not manifest:
            raise ValueError("Primero abre el archivo de una sede.")
        if not isinstance(student_fields, dict) or not isinstance(
            enrollment_fields, dict
        ):
            raise ValueError("Los datos de la matrícula no tienen un formato válido.")

        working = deepcopy(manifest)
        student_id = str(student_fields.get("id") or "").strip()
        student_created = False
        student_change = None
        if student_id:
            if not any(
                item["id"] == student_id for item in working["students"]
            ):
                raise ValueError("Selecciona un estudiante válido.")
        else:
            student_change = self._record_service.save_student(
                working,
                "",
                str(student_fields.get("last_name") or ""),
                str(student_fields.get("first_name") or ""),
                str(student_fields.get("document_number") or ""),
                str(student_fields.get("phone_text") or ""),
            )
            student_id = str(student_change.record["id"])
            student_created = True

        fields = dict(enrollment_fields)
        fields["student_id"] = student_id
        enrollment_change = self._record_service.save_enrollment(
            working, "", fields
        )
        enrollment_id = str(enrollment_change.record["id"])
        return EnrollmentCreation(
            manifest=working,
            student_id=student_id,
            enrollment_id=enrollment_id,
            student_created=student_created,
            student_change=student_change,
            enrollment_change=enrollment_change,
        )
