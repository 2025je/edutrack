import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

PHONE_PATTERN = re.compile(r"9\d{8}\Z")


class RecordService:
    def normalize_course_fields(
        self,
        manifest: dict[str, Any],
        course_id: int | None,
        name: str,
        schedule: str,
        group_name: str,
        start_date: str,
        enrollment_fee: str,
        monthly_fee: str,
        capacity: str,
    ) -> dict[str, Any]:
        raw_name = name.strip()
        raw_schedule = schedule.strip()
        raw_group = group_name.strip()
        if (
            not raw_name
            or len(raw_name) > 120
            or not raw_schedule
            or len(raw_schedule) > 120
            or len(raw_group) > 50
        ):
            raise ValueError("Ingresa un nombre de curso y un horario válidos.")
        name = " ".join(raw_name.split()).upper()
        schedule = " ".join(raw_schedule.split()).upper()
        try:
            group_name = str(int(raw_group)) if raw_group.isdigit() else ""
        except ValueError:
            group_name = ""
        if not name or not schedule:
            raise ValueError("Ingresa un nombre de curso y un horario válidos.")
        if not group_name or int(group_name) < 1 or len(group_name) > 50:
            raise ValueError("El grupo debe ser un número entero positivo.")
        try:
            date_text = start_date.strip()
            parsed_course_date = date.fromisoformat(date_text)
            if parsed_course_date.isoformat() != date_text:
                raise ValueError("La fecha de inicio no es válida.")
            normalized_course_date = parsed_course_date.isoformat()
            enrollment_fee = self._amount(enrollment_fee, "costo de matrícula")
            monthly_fee = self._amount(monthly_fee, "mensualidad")
            parsed_capacity = int(capacity)
            if parsed_capacity < 1 or parsed_capacity > 2_147_483_647:
                raise ValueError("La capacidad debe ser un entero positivo.")
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(str(exc) or "Revisa los datos del curso.") from exc
        if any(
            item["id"] != course_id
            and item["name"].strip().casefold() == name.casefold()
            and item["schedule"].strip().casefold() == schedule.casefold()
            and str(item["group"]).strip() == group_name
            for item in manifest["courses"]
        ):
            raise ValueError("Ya existe un curso con el mismo nombre, horario y grupo.")
        return {
            "name": name,
            "schedule": schedule,
            "group": group_name,
            "start_date": normalized_course_date,
            "enrollment_fee": enrollment_fee,
            "monthly_fee": monthly_fee,
            "capacity": parsed_capacity,
        }

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
    ) -> int:
        fields = self.normalize_course_fields(
            manifest,
            None,
            name,
            schedule,
            group_name,
            start_date,
            enrollment_fee,
            monthly_fee,
            capacity,
        )
        course_id = (
            max((int(item["id"]) for item in manifest["courses"]), default=0) + 1
        )
        manifest["courses"].append(
            {"id": course_id, "server_id": None, **fields, "active": True}
        )
        return course_id

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
    ) -> None:
        course = next(
            (item for item in manifest["courses"] if item["id"] == course_id),
            None,
        )
        if course is None:
            raise ValueError("Selecciona un curso válido para editar.")
        fields = self.normalize_course_fields(
            manifest,
            course_id,
            name,
            schedule,
            group_name,
            start_date,
            enrollment_fee,
            monthly_fee,
            capacity,
        )
        course.update(fields)
        course["active"] = active

    def create_promoter(self, manifest: dict[str, Any], name: str) -> int:
        if manifest.get("campus_mode") != "new":
            raise ValueError(
                "Los promotores se crean desde Desktop al preparar una sede nueva."
            )
        name = name.strip().upper()
        if not name or len(name) > 120:
            raise ValueError("Ingresa un nombre de promotor válido.")
        if any(
            item["name"].strip().casefold() == name.casefold()
            for item in manifest["promoters"]
        ):
            raise ValueError("Ya existe un promotor con ese nombre.")
        promoter_id = (
            max((int(item["id"]) for item in manifest["promoters"]), default=0) + 1
        )
        manifest["promoters"].append(
            {"id": promoter_id, "server_id": None, "name": name, "active": True}
        )
        return promoter_id

    def save_student(
        self,
        manifest: dict[str, Any],
        source_id: str,
        last_name: str,
        first_name: str,
        document_number: str,
        phone_text: str,
    ) -> str:
        last_name = last_name.strip().upper()
        first_name = first_name.strip().upper()
        document_number = document_number.strip()
        phones = [value.strip() for value in phone_text.split(",") if value.strip()]
        if not last_name or not first_name:
            raise ValueError("Apellidos y nombres son obligatorios.")
        if len(last_name) > 120 or len(first_name) > 120 or len(document_number) > 20:
            raise ValueError("Revisa la longitud de apellidos, nombres o DNI.")
        if not phones or any(not PHONE_PATTERN.fullmatch(phone) for phone in phones):
            raise ValueError("Ingresa uno o más celulares peruanos de 9 dígitos.")
        if len(set(phones)) != len(phones):
            raise ValueError("No repitas un teléfono.")
        row = next(
            (item for item in manifest["students"] if item["id"] == source_id),
            None,
        )
        full_name = f"{last_name} {first_name}".strip().casefold()
        duplicate = any(
            item is not row
            and " ".join(
                part
                for part in (
                    str(item.get("last_name", "")).strip(),
                    str(item.get("first_name", "")).strip(),
                )
                if part
            )
            .strip()
            .casefold()
            == full_name
            for item in manifest["students"]
        )
        if duplicate:
            raise ValueError("Ya existe un estudiante con estos apellidos y nombres.")
        if row is None:
            row = {
                "id": str(uuid.uuid4()),
                "server_id": None,
                "base_hash": None,
                "active": True,
            }
            manifest["students"].append(row)
        row.update(
            {
                "last_name": last_name,
                "first_name": first_name,
                "document_number": document_number,
                "phone_numbers": phones,
            }
        )
        return row["id"]

    def save_enrollment(
        self, manifest: dict[str, Any], source_id: str, fields: dict[str, Any]
    ) -> str:
        row = next(
            (item for item in manifest["enrollments"] if item["id"] == source_id),
            None,
        )
        if source_id and row is None:
            raise ValueError("La matrícula seleccionada ya no existe.")
        try:
            student_id = str(fields.get("student_id") or "").strip() or None
            course_id = self._optional_integer(fields.get("course_id"), "curso")
            student = next(
                (
                    item
                    for item in manifest["students"]
                    if item["id"] == student_id
                ),
                None,
            )
            course = next(
                (item for item in manifest["courses"] if item["id"] == course_id),
                None,
            )
            if student_id and student is None:
                raise ValueError("Selecciona un estudiante válido.")
            if course_id and course is None:
                raise ValueError("Selecciona un curso válido.")
            if not student_id and not course_id:
                raise ValueError("La matrícula requiere un estudiante o un curso.")
            if row and row.get("student_id") and not student_id:
                raise ValueError(
                    "Una matrícula que ya tiene estudiante no puede quedarse sin él."
                )
            date_text = str(fields.get("enrollment_date", "")).strip()
            enrollment_date = date.fromisoformat(date_text)
            if enrollment_date.isoformat() != date_text:
                raise ValueError("La fecha de matrícula no es válida.")
            if course_id:
                enrollment_fee = self._amount(
                    fields.get("enrollment_fee"), "costo de matrícula"
                )
                monthly_fee = self._amount(fields.get("monthly_fee"), "mensualidad")
            else:
                enrollment_fee = monthly_fee = "0.00"
            code_text = str(
                fields.get(
                    "record_code",
                    row.get("record_code", "") if row else "",
                )
                or ""
            ).strip()
            if code_text and (
                len(code_text) > 50
                or not code_text.isascii()
                or not code_text.isdigit()
            ):
                raise ValueError("Ingrese solo números en el código de ficha.")
            record_code = int(code_text) if code_text else None
            if record_code is not None and not 0 < record_code <= 2_147_483_647:
                raise ValueError("El código de ficha debe ser un entero positivo.")
            raw_promoter_ids = (
                fields.get(
                    "promoter_ids",
                    row.get("promoter_ids", []) if row else [],
                )
                or []
            )
            if not isinstance(raw_promoter_ids, (list, tuple)):
                raise ValueError("Selecciona promotores válidos.")
            if any(isinstance(value, bool) for value in raw_promoter_ids):
                raise ValueError("Selecciona promotores válidos.")
            promoter_ids = [int(value) for value in raw_promoter_ids]
            if len(set(promoter_ids)) != len(promoter_ids):
                raise ValueError("Una matrícula no puede repetir promotores.")
            promoters_by_id = {item["id"]: item for item in manifest["promoters"]}
            if any(value not in promoters_by_id for value in promoter_ids):
                raise ValueError("Selecciona promotores válidos.")
            quality_text = str(
                fields.get(
                    "record_image_quality",
                    row.get("record_image_quality", 80) if row else 80,
                )
            ).strip()
            if quality_text not in ("60", "80", "90"):
                raise ValueError("La calidad de imagen de ficha no es válida.")
            record_image_quality = int(quality_text)
        except (ValueError, InvalidOperation, TypeError) as exc:
            raise ValueError(str(exc) or "Revisa los datos de la matrícula.") from exc

        if (
            student
            and not student["active"]
            and (not row or row.get("student_id") != student_id)
        ):
            raise ValueError("No se puede matricular a un estudiante inactivo.")
        if (
            course
            and not course["active"]
            and (not row or row.get("course_id") != course_id)
        ):
            raise ValueError("No se pueden crear matrículas en un curso inactivo.")
        if (
            student_id
            and course_id
            and any(
                item is not row
                and item.get("student_id") == student_id
                and item.get("course_id") == course_id
                for item in manifest["enrollments"]
            )
        ):
            raise ValueError("Este estudiante ya está matriculado en este curso.")
        if record_code is not None and any(
            item is not row
            and item.get("record_code") not in (None, "")
            and int(item["record_code"]) == record_code
            and item.get("enrollment_date") == enrollment_date.isoformat()
            for item in manifest["enrollments"]
        ):
            raise ValueError(
                "Este código de ficha ya está registrado en la misma fecha de matrícula."
            )
        if any(
            not promoters_by_id[pk]["active"]
            and (not row or pk not in row.get("promoter_ids", []))
            for pk in promoter_ids
        ):
            raise ValueError("No se pueden asignar promotores inactivos.")
        if len(promoter_ids) > 1 and any(
            promoters_by_id[pk]["name"].upper() in ("PARTICULAR", "NN")
            for pk in promoter_ids
        ):
            raise ValueError(
                "PARTICULAR y NN no se pueden combinar con otros promotores."
            )

        if row is None:
            row = {
                "id": str(uuid.uuid4()),
                "server_id": None,
                "base_hash": None,
                "active": True,
                "record_image": None,
                "record_image_hash": "",
                "record_image_quality": 80,
            }
            manifest["enrollments"].append(row)
        if not record_code:
            row["record_image"] = None
            row["record_image_hash"] = ""
            self.remove_unused_attachments(manifest)
        row.update(
            {
                "student_id": student_id,
                "student_server_id": student["server_id"] if student else None,
                "course_id": course_id,
                "enrollment_date": enrollment_date.isoformat(),
                "promoter_ids": promoter_ids,
                "enrollment_fee": enrollment_fee,
                "monthly_fee": monthly_fee,
                "record_code": record_code,
                "record_image_quality": record_image_quality,
            }
        )
        return row["id"]

    @staticmethod
    def remove_unused_attachments(manifest: dict[str, Any]) -> None:
        referenced = {
            row["record_image"]
            for row in manifest["enrollments"]
            if row.get("record_image")
        }
        attachments = manifest.get("_attachment_data", {})
        manifest["_attachment_data"] = {
            path: content for path, content in attachments.items() if path in referenced
        }

    @staticmethod
    def _optional_integer(value: Any, label: str) -> int | None:
        if value in (None, ""):
            return None
        result = int(value)
        if result < 1:
            raise ValueError(f"El {label} seleccionado no es válido.")
        return result

    @staticmethod
    def _amount(value: Any, label: str) -> str:
        try:
            amount = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValueError(f"El {label} no es válido.") from exc
        decimal_tuple = amount.as_tuple()
        if not amount.is_finite() or amount < Decimal("0.01") or amount >= Decimal(
            "100000000"
        ):
            raise ValueError(
                f"El {label} debe ser mayor que cero y tener hasta 2 decimales."
            )
        if (
            not isinstance(decimal_tuple.exponent, int)
            or decimal_tuple.exponent < -2
            or len(decimal_tuple.digits) > 10
        ):
            raise ValueError(
                f"El {label} debe ser mayor que cero y tener hasta 2 decimales."
            )
        return format(amount, ".2f")
