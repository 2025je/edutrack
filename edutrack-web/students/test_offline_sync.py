import hashlib
import io
import tempfile
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from core.models import Campus, User
from core.testing import create_user, grant
from students.models import Course, Enrollment, Ficha, Promoter, Student
from students.offline_sync import (
    OfflinePackageError,
    export_campus,
    import_initial_package,
    import_package,
    package_bytes,
    parse_package,
    review_courses,
    review_package,
)


class OfflineSynchronizationTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Offline")
        self.user = User.objects.create_user(username="offline-importer", password="test-pass")
        self.course = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Mañana",
            group="1",
            start_date=date(2026, 1, 1),
            enrollment_fee="100.00",
            monthly_fee="80.00",
        )
        self.promoter = Promoter.objects.create(name="Promotor Offline")
        self.promoter.campuses.add(self.campus)
        self.student = Student.objects.create(
            campus=self.campus,
            last_name="Pérez",
            first_name="Ana",
            full_name="Pérez Ana",
            document_number="12345678",
            phone="987654321",
        )
        self.enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=self.student,
            course=self.course,
            enrollment_date=date(2026, 1, 2),
            enrollment_fee="100.00",
            monthly_fee="80.00",
        )
        self.enrollment.promoter.add(self.promoter)

    def package_from(self, manifest, attachments=None):
        return parse_package(package_bytes(manifest, attachments))

    def initial_manifest(self):
        student_id = str(uuid.uuid4())
        return {
            "format": "edutrack-offline",
            "version": 3,
            "campus_mode": "new",
            "bundle_id": str(uuid.uuid4()),
            "campus_id": None,
            "campus_name": "Sede inicial",
            "campus_address": "Av. Principal 123",
            "students": [
                {
                    "id": student_id,
                    "server_id": None,
                    "base_hash": None,
                    "last_name": "Pérez",
                    "first_name": "Ana",
                    "document_number": "12345678",
                    "phone_numbers": ["987654321"],
                    "active": True,
                }
            ],
            "enrollments": [
                {
                    "id": str(uuid.uuid4()),
                    "server_id": None,
                    "base_hash": None,
                    "student_id": student_id,
                    "student_server_id": None,
                    "course_id": 1,
                    "enrollment_date": "2026-01-02",
                    "promoter_ids": [1],
                    "enrollment_fee": "100.00",
                    "monthly_fee": "80.00",
                    "record_code": None,
                    "active": True,
                }
            ],
            "courses": [
                {
                    "id": 1,
                    "server_id": None,
                    "name": "Matemáticas",
                    "schedule": "Mañana",
                    "group": "1",
                    "start_date": "2026-01-01",
                    "enrollment_fee": "100.00",
                    "monthly_fee": "80.00",
                    "capacity": 20,
                    "active": True,
                }
            ],
            "promoters": [
                {"id": 1, "server_id": None, "name": "PARTICULAR", "active": True},
                {"id": 2, "server_id": None, "name": "NN", "active": True},
            ],
        }

    def test_initial_package_creates_campus_catalog_and_records_atomically(self):
        package = self.package_from(self.initial_manifest())
        user = create_user(
            username="initial-importer",
            password="test-password",
            manage_students=True,
            manage_campuses=True,
        )
        request = SimpleNamespace(
            method="POST",
            user=user,
            session={},
        )

        with patch("core.activity.record"):
            campus, result = import_initial_package(package, request)

        self.assertEqual(campus.name, "Sede inicial")
        self.assertEqual(campus.address, "Av. Principal 123")
        self.assertEqual(str(campus.desktop_bundle_id), package["bundle_id"])
        self.assertTrue(campus.users.filter(pk=user.pk).exists())
        self.assertEqual(request.session["selected_campus_id"], campus.pk)
        self.assertEqual(result, (1, 0, 1, 0))
        self.assertTrue(Course.objects.filter(campus=campus, name="MATEMÁTICAS").exists())
        self.assertEqual(Student.objects.filter(campus=campus).count(), 1)
        self.assertEqual(Enrollment.objects.filter(campus=campus).count(), 1)
        with self.assertRaisesMessage(OfflinePackageError, "ya fue importado"):
            import_initial_package(package, request)
        self.assertEqual(Campus.objects.filter(desktop_bundle_id=package["bundle_id"]).count(), 1)

    def test_initial_package_accepts_pending_enrollment_and_reserved_seat(self):
        manifest = self.initial_manifest()
        existing = manifest["enrollments"][0]
        pending = {
            **existing,
            "id": str(uuid.uuid4()),
            "course_id": None,
            "enrollment_fee": "9.00",
            "monthly_fee": "8.00",
        }
        reserved_seat = {
            **existing,
            "id": str(uuid.uuid4()),
            "student_id": None,
            "student_server_id": None,
        }
        manifest["enrollments"].extend((pending, reserved_seat))
        package = self.package_from(manifest)
        user = create_user(
            username="pending-importer",
            password="test-pass-123",
            manage_students=True,
            manage_campuses=True,
        )
        request = SimpleNamespace(method="POST", user=user, session={})

        with patch("core.activity.record"):
            campus, _ = import_initial_package(package, request)

        enrollments = list(Enrollment.objects.filter(campus=campus))
        self.assertEqual(len(enrollments), 3)
        self.assertTrue(
            any(
                item.student_id is not None
                and item.course_id is None
                and item.enrollment_fee == 0
                and item.monthly_fee == 0
                for item in enrollments
            )
        )
        self.assertTrue(
            any(item.student_id is None and item.course_id is not None for item in enrollments)
        )

    def test_package_rejects_enrollment_without_student_and_course(self):
        manifest = self.initial_manifest()
        manifest["enrollments"][0]["student_id"] = None
        manifest["enrollments"][0]["student_server_id"] = None
        manifest["enrollments"][0]["course_id"] = None

        with self.assertRaisesRegex(OfflinePackageError, "necesita un estudiante o un curso"):
            self.package_from(manifest)

    def test_invalid_initial_catalog_rolls_back_campus_and_restores_selection(self):
        manifest = self.initial_manifest()
        manifest["promoters"][0]["active"] = False
        package = self.package_from(manifest)
        user = create_user(
            username="failed-initial-importer",
            password="test-password",
            manage_students=True,
            manage_campuses=True,
        )
        request = SimpleNamespace(
            method="POST",
            user=user,
            session={"selected_campus_id": self.campus.pk},
        )

        with self.assertRaisesMessage(OfflinePackageError, "otro estado"):
            import_initial_package(package, request)

        self.assertFalse(Campus.objects.filter(name="Sede inicial").exists())
        self.assertEqual(Course.objects.filter(campus__name="Sede inicial").count(), 0)
        self.assertEqual(request.session["selected_campus_id"], self.campus.pk)

    def test_initial_import_page_and_download_work_without_preselected_campus(self):
        user = create_user(
            username="initial-web-import",
            password="test-password",
            manage_students=True,
            manage_campuses=True,
        )
        self.client.force_login(user)
        manifest = self.initial_manifest()
        payload = package_bytes(manifest)

        page = self.client.get(reverse("desktop-import"))
        preview = self.client.post(
            reverse("desktop-import"),
            {
                "action": "preview",
                "package": SimpleUploadedFile("initial.edutrack", payload),
            },
        )

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Sube aquí un paquete inicial")
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Crear sede: Sede inicial")
        with patch("core.activity.record"):
            result = self.client.post(
                reverse("desktop-import"),
                {
                    "action": "confirm",
                    "token": preview.context["import_token"],
                },
            )

        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Sede creada e importación completada")
        selected_campus = self.client.session["selected_campus_id"]
        exported = self.client.get(reverse("desktop-campus-export"))
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(parse_package(exported.content)["campus_id"], selected_campus)

    def test_web_export_contains_full_campus_snapshot(self):
        manifest, attachments = export_campus(self.campus)
        package = self.package_from(manifest, attachments)

        self.assertEqual(package["campus_id"], self.campus.pk)
        self.assertEqual(len(package["students"]), 1)
        self.assertEqual(len(package["enrollments"]), 1)
        self.assertEqual(package["enrollments"][0]["student_id"], package["students"][0]["id"])
        self.assertEqual(package["enrollments"][0]["course_id"], self.course.pk)
        self.assertEqual(package["courses"][0]["id"], self.course.pk)
        self.assertEqual(package["courses"][0]["server_id"], self.course.pk)
        self.assertIn(self.promoter.pk, [row["id"] for row in package["promoters"]])
        self.assertTrue(package["students"][0]["base_hash"])
        self.assertTrue(package["enrollments"][0]["base_hash"])

    def test_web_download_and_import_page_are_available_to_enrollment_staff(self):
        user = create_user(
            username="offline-web",
            password="test-pass",
            manage_students=True,
        )
        user.campuses.add(self.campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

        export_response = self.client.get(reverse("desktop-campus-export"))
        page_response = self.client.get(reverse("desktop-import"))

        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(
            export_response["Content-Disposition"],
            f'attachment; filename="edutrack-sede-{self.campus.pk}.edutrack"',
        )
        self.assertEqual(len(parse_package(export_response.content)["students"]), 1)
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Descargar datos de esta sede")

    def test_conflicts_can_be_resolved_per_record(self):
        manifest, _ = export_campus(self.campus)
        row = manifest["students"][0]
        row["first_name"] = "Versión Desktop"
        self.student.first_name = "Versión Web"
        self.student.full_name = "Pérez Versión Web"
        self.student.save()
        package = self.package_from(manifest)

        unresolved, _ = review_package(package, self.campus)
        self.assertEqual(unresolved[0]["state"], "conflict")
        self.assertTrue(unresolved[0]["resolvable"])

        keep_web, _ = review_package(package, self.campus, {f"student:{row['id']}": "web"})
        self.assertEqual(keep_web[0]["state"], "unchanged")

        use_desktop, _ = review_package(package, self.campus, {f"student:{row['id']}": "desktop"})
        self.assertEqual(use_desktop[0]["state"], "update")

    def test_sync_updates_existing_and_creates_new_records(self):
        manifest, _ = export_campus(self.campus)
        existing = manifest["students"][0]
        existing["first_name"] = "ANA ACTUALIZADA"
        new_student_id = str(uuid.uuid4())
        new_enrollment_id = str(uuid.uuid4())
        manifest["students"].append(
            {
                "id": new_student_id,
                "server_id": None,
                "base_hash": None,
                "last_name": "García",
                "first_name": "Luis",
                "document_number": "87654321",
                "phone_numbers": ["912345678"],
                "active": True,
            }
        )
        manifest["enrollments"].append(
            {
                "id": new_enrollment_id,
                "server_id": None,
                "base_hash": None,
                "student_id": new_student_id,
                "student_server_id": None,
                "course_id": self.course.pk,
                "enrollment_date": "2026-01-03",
                "promoter_ids": [self.promoter.pk],
                "enrollment_fee": "100.00",
                "monthly_fee": "80.00",
                "record_code": None,
                "active": True,
            }
        )
        package = self.package_from(manifest)
        request = SimpleNamespace(
            method="POST",
            user=self.user,
            session={"selected_campus_id": self.campus.pk},
        )

        with patch("core.activity.record"):
            result = import_package(package, self.campus, request)

        self.assertEqual(result, (0, 1, 1, 1, 0))
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "ANA ACTUALIZADA")
        created_student = Student.objects.get(document_number="87654321")
        created_enrollment = Enrollment.objects.get(student=created_student)
        self.assertEqual(created_enrollment.course, self.course)
        self.assertEqual(created_enrollment.installments.count(), 2)

    def test_sync_creates_new_course_and_links_new_enrollment(self):
        manifest, _ = export_campus(self.campus)
        new_course_id = max(course["id"] for course in manifest["courses"]) + 1
        manifest["courses"].append(
            {
                "id": new_course_id,
                "server_id": None,
                "name": "COMUNICACIÓN",
                "schedule": "TARDE",
                "group": "2",
                "start_date": "2026-03-01",
                "enrollment_fee": "50.00",
                "monthly_fee": "40.00",
                "capacity": 15,
                "active": True,
            }
        )
        new_student_id = str(uuid.uuid4())
        new_enrollment_id = str(uuid.uuid4())
        manifest["students"].append(
            {
                "id": new_student_id,
                "server_id": None,
                "base_hash": None,
                "last_name": "Torres",
                "first_name": "Luz",
                "document_number": "87654321",
                "phone_numbers": ["912345678"],
                "active": True,
            }
        )
        manifest["enrollments"].append(
            {
                "id": new_enrollment_id,
                "server_id": None,
                "base_hash": None,
                "student_id": new_student_id,
                "student_server_id": None,
                "course_id": new_course_id,
                "enrollment_date": "2026-03-02",
                "promoter_ids": [],
                "enrollment_fee": "50.00",
                "monthly_fee": "40.00",
                "record_code": None,
                "record_image": None,
                "record_image_hash": "",
                "record_image_quality": 80,
                "active": True,
            }
        )
        package = self.package_from(manifest)

        course_rows, _ = review_courses(package, self.campus)
        new_course_row = next(row for row in course_rows if row["source_id"] == new_course_id)
        self.assertEqual(new_course_row["state"], "new")
        _, enrollment_rows = review_package(package, self.campus)
        new_enrollment_row = next(
            row for row in enrollment_rows if row["source_id"] == new_enrollment_id
        )
        self.assertEqual(new_enrollment_row["state"], "new")

        request = SimpleNamespace(
            method="POST",
            user=self.user,
            session={"selected_campus_id": self.campus.pk},
        )
        with patch("core.activity.record"):
            result = import_package(package, self.campus, request)

        self.assertEqual(result, (1, 1, 0, 1, 0))
        new_course = Course.objects.get(campus=self.campus, name="COMUNICACIÓN", group="2")
        new_student = Student.objects.get(document_number="87654321")
        new_enrollment = Enrollment.objects.get(student=new_student)
        self.assertEqual(new_enrollment.course, new_course)
        repeated_rows, repeated_map = review_courses(package, self.campus)
        repeated_course_row = next(
            row for row in repeated_rows if row["source_id"] == new_course_id
        )
        self.assertEqual(repeated_course_row["state"], "unchanged")
        self.assertEqual(repeated_map[new_course_id], new_course)

    def test_existing_course_addition_requires_permission_and_imports_from_preview(self):
        manifest, _ = export_campus(self.campus)
        new_course_id = max(course["id"] for course in manifest["courses"]) + 1
        manifest["courses"].append(
            {
                "id": new_course_id,
                "server_id": None,
                "name": "CIENCIAS",
                "schedule": "NOCHE",
                "group": "3",
                "start_date": "2026-04-01",
                "enrollment_fee": "60.00",
                "monthly_fee": "45.00",
                "capacity": 18,
                "active": True,
            }
        )
        payload = package_bytes(manifest)
        user = create_user(username="course-importer", manage_students=True)
        user.campuses.add(self.campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

        denied_preview = self.client.post(
            reverse("desktop-import"),
            {
                "action": "preview",
                "package": SimpleUploadedFile("courses.edutrack", payload),
            },
        )

        self.assertEqual(denied_preview.status_code, 200)
        self.assertContains(denied_preview, "No tienes permiso para crear cursos.")
        self.assertNotContains(denied_preview, "Confirmar sincronización")

        grant(user, "manage_promoters")
        allowed_preview = self.client.post(
            reverse("desktop-import"),
            {
                "action": "preview",
                "package": SimpleUploadedFile("courses.edutrack", payload),
            },
        )
        self.assertContains(allowed_preview, "Confirmar sincronización")
        with patch("core.activity.record"):
            result = self.client.post(
                reverse("desktop-import"),
                {
                    "action": "confirm",
                    "token": allowed_preview.context["import_token"],
                },
            )

        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Cursos: 1 creados.")
        self.assertTrue(
            Course.objects.filter(
                campus=self.campus, name="CIENCIAS", schedule="NOCHE", group="3"
            ).exists()
        )

    def test_ficha_image_round_trips_and_can_be_replaced_offline(self):
        def image_bytes(color):
            output = io.BytesIO()
            Image.new("RGB", (4, 3), color).save(output, format="JPEG")
            return output.getvalue()

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                original = image_bytes("red")
                ficha = Ficha(
                    enrollment=self.enrollment,
                    campus=self.campus,
                    date=self.enrollment.enrollment_date,
                    code=17,
                )
                ficha.image.save("original.jpg", ContentFile(original), save=False)
                ficha.save()
                manifest, attachments = export_campus(self.campus)
                row = manifest["enrollments"][0]
                self.assertIn(row["record_image"], attachments)

                replacement = image_bytes("blue")
                replacement_path = f"attachments/{hashlib.sha256(replacement).hexdigest()}.jpg"
                row["record_image"] = replacement_path
                row["record_image_hash"] = hashlib.sha256(replacement).hexdigest()
                row["monthly_fee"] = "85.00"
                package = self.package_from(manifest, {replacement_path: replacement})
                _, enrollment_rows = review_package(package, self.campus)
                self.assertEqual(enrollment_rows[0]["state"], "update")

                request = SimpleNamespace(
                    method="POST",
                    user=self.user,
                    session={"selected_campus_id": self.campus.pk},
                )
                with patch("core.activity.record"):
                    import_package(package, self.campus, request)

                ficha.refresh_from_db()
                with ficha.image.open("rb") as stored:
                    with Image.open(stored) as saved_image:
                        self.assertEqual(saved_image.size, (4, 3))
