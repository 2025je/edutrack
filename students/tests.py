from datetime import date
from io import BytesIO

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.http import QueryDict
from django.utils import timezone
from openpyxl import load_workbook

from core.models import Campus, User
from payments.models import Installment, Payment, PaymentAllocation
from students.forms import PhoneListWidget
from students.models import Course, Enrollment, Ficha, Promoter, Schedule, Student


class CourseStudentExportTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Exportación", active=True)
        self.user = User.objects.create_user(
            username="exporter",
            password="secret123",
            can_manage_students=True,
        )
        self.user.campuses.add(self.campus)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

        self.student_a = Student.objects.create(
            campus=self.campus,
            full_name="Ana Pérez",
            document_number="12345678",
            phone="987654321",
        )
        self.student_b = Student.objects.create(
            campus=self.campus,
            full_name="Luis Gómez",
            document_number="87654321",
            phone="912345678",
        )
        self.student_c = Student.objects.create(
            campus=self.campus,
            full_name="Marta Ruiz",
            document_number="23456789",
            phone="923456789",
        )
        self.course_a = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Lunes",
            group="A",
            start_date=date(2026, 10, 1),
        )
        course_b = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Miércoles",
            group="B",
            start_date=date(2026, 10, 1),
        )
        course_c = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Martes",
            group="C",
            start_date=date(2026, 10, 1),
        )
        course_d = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Jueves",
            group="D",
            start_date=date(2026, 10, 1),
        )
        course_e = Course.objects.create(
            campus=self.campus,
            name="Matemáticas",
            schedule="Viernes",
            group="E",
            start_date=date(2026, 10, 1),
        )
        course_f = Course.objects.create(
            campus=self.campus,
            name="Historia",
            schedule="Viernes",
            group="F",
            start_date=date(2026, 10, 1),
        )
        Course.objects.create(
            campus=self.campus,
            name="Física",
            schedule="Sábado",
            group="G",
            start_date=date(2026, 10, 1),
        )
        Enrollment.objects.create(campus=self.campus, student=self.student_a, course=self.course_a)
        Enrollment.objects.create(campus=self.campus, student=self.student_b, course=self.course_a)
        Enrollment.objects.create(campus=self.campus, student=self.student_b, course=course_b)
        Enrollment.objects.create(campus=self.campus, student=self.student_c, course=course_c)
        Enrollment.objects.create(campus=self.campus, student=self.student_a, course=course_d)
        Enrollment.objects.create(campus=self.campus, student=self.student_b, course=course_e)
        Enrollment.objects.create(campus=self.campus, student=self.student_c, course=course_f)

    def test_export_creates_one_sheet_per_course_name(self):
        response = self.client.get(reverse("course-student-export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        self.assertEqual(workbook.sheetnames, ["HISTORIA", "MATEMÁTICAS"])
        self.assertNotIn("FÍSICA", workbook.sheetnames)
        math_rows = list(workbook["MATEMÁTICAS"].iter_rows(values_only=True))
        history_rows = list(workbook["HISTORIA"].iter_rows(values_only=True))
        self.assertEqual(len(workbook["MATEMÁTICAS"].tables), 5)
        self.assertEqual(len(workbook["HISTORIA"].tables), 1)
        self.assertIn("ANA PÉREZ", [value for row in math_rows for value in row])
        self.assertIn("LUIS GÓMEZ", [value for row in math_rows for value in row])
        math_values = [value for row in math_rows for value in row]
        for group in ("A", "B", "C", "D", "E"):
            self.assertTrue(
                any(
                    isinstance(value, str) and value.startswith(f"Grupo: {group} ·")
                    for value in math_values
                )
            )
        self.assertIn("MARTA RUIZ", [value for row in history_rows for value in row])
        math_table = workbook["MATEMÁTICAS"].tables[f"Course_{self.course_a.pk}"]
        header_row = int(math_table.ref.split(":")[0][1:])
        self.assertEqual(
            [workbook["MATEMÁTICAS"].cell(header_row, column).value for column in range(1, 6)],
            ["N.º", "Alumno", "DNI", "Teléfonos", "Fecha de matrícula"],
        )
        self.assertEqual(workbook["MATEMÁTICAS"].cell(header_row + 1, 1).value, 1)
        self.assertEqual(workbook["MATEMÁTICAS"].cell(header_row + 2, 1).value, 2)


class StudentEnrollmentCrudTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede CRUD", active=True)
        self.user = User.objects.create_user(
            username="manager",
            password="secret123",
            can_manage_students=True,
            can_register_payments=True,
        )
        self.user.campuses.add(self.campus)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()
        self.student = Student.objects.create(
            campus=self.campus,
            full_name="Estudiante de prueba",
            document_number="11112222",
            phone="987654321",
        )
        self.course = Course.objects.create(
            campus=self.campus,
            name="Curso de prueba",
            start_date=date(2026, 10, 14),
            enrollment_fee=40,
            monthly_fee=60,
        )
        self.enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=self.student,
            course=self.course,
            enrollment_fee=40,
            monthly_fee=60,
        )

    def add_payment_history(self):
        installment = Installment.objects.create(
            enrollment=self.enrollment,
            concept="Cuota de prueba",
            amount=100,
            due_date=date(2026, 10, 14),
        )
        payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="CRUD-001",
            amount=40,
        )
        allocation = PaymentAllocation.objects.create(
            payment=payment,
            installment=installment,
            amount=40,
        )
        return installment, payment, allocation

    def test_student_and_enrollment_can_be_updated(self):
        response = self.client.get(reverse("student-update", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("student-update", args=[self.student.pk]),
            {
                "last_name": "Apellidos actualizados",
                "first_name": "Nombres",
                "document_number": self.student.document_number,
                "phone_numbers": self.student.phone,
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "APELLIDOS ACTUALIZADOS NOMBRES")

        response = self.client.get(reverse("enrollment-update", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("enrollment-update", args=[self.enrollment.pk]),
            {
                "course": self.course.pk,
                "student": self.student.pk,
                "record_code": "202601",
                "promoter": [],
                "enrollment_date": self.enrollment.enrollment_date.isoformat(),
                "enrollment_fee": "40.00",
                "monthly_fee": "60.00",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.record_code, 202601)

    def test_enrollment_record_code_accepts_only_numbers_or_empty(self):
        response = self.client.post(
            reverse("enrollment-update", args=[self.enrollment.pk]),
            {
                "course": self.course.pk,
                "student": self.student.pk,
                "record_code": "F-2026-01",
                "promoter": [],
                "enrollment_date": self.enrollment.enrollment_date.isoformat(),
                "enrollment_fee": "40.00",
                "monthly_fee": "60.00",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingrese solo números en el código de ficha.")
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.record_code, "")

    def test_ficha_exists_only_when_record_code_is_given(self):
        base = {
            "course": self.course.pk,
            "student": self.student.pk,
            "promoter": [],
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "40.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        url = reverse("enrollment-update", args=[self.enrollment.pk])
        for data in ({"record_code": "0"}, {"record_code": "-3"}, {"record_code": "abc"}):
            response = self.client.post(url, {**base, **data})
            self.assertEqual(response.status_code, 200, data)
            self.assertTrue(response.context["form"].errors.get("record_code"), data)

        # Sin código no se crea ficha.
        self.assertEqual(self.client.post(url, {**base, "record_code": ""}).status_code, 302)
        self.assertFalse(Ficha.objects.filter(enrollment=self.enrollment).exists())
        response = self.client.post(url, {**base, "record_code": "15"})
        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.has_record)
        self.assertEqual(self.enrollment.record_code, 15)

    def test_ficha_image_is_optional_and_can_be_replaced_and_removed(self):
        import io
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from PIL import Image

        def png(name):
            buffer = io.BytesIO()
            Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
            return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

        base = {
            "course": self.course.pk,
            "student": self.student.pk,
            "record_code": "77",
            "promoter": [],
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "40.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        url = reverse("enrollment-update", args=[self.enrollment.pk])
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            self.assertEqual(self.client.post(url, base).status_code, 302)
            ficha = Ficha.objects.get(enrollment=self.enrollment)
            self.assertFalse(ficha.image)

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, {**base, "record_image": png("a.png")})
            self.assertEqual(response.status_code, 302)
            ficha.refresh_from_db()
            first = ficha.image.name
            self.assertTrue(first.startswith("fichas/"))
            self.assertTrue(first.endswith(".jpg"))
            with ficha.image.open("rb") as handle:
                self.assertEqual(Image.open(handle).format, "JPEG")

            big = io.BytesIO()
            import random

            noise = Image.frombytes(
                "RGB", (400, 400), bytes(random.randrange(256) for _ in range(400 * 400 * 3))
            )
            noise.save(big, "PNG")
            sizes = {}
            for quality in ("90", "60"):
                upload = SimpleUploadedFile("n.png", big.getvalue(), content_type="image/png")
                with self.captureOnCommitCallbacks(execute=True):
                    self.client.post(
                        url, {**base, "record_image": upload, "record_image_quality": quality}
                    )
                ficha.refresh_from_db()
                sizes[quality] = ficha.image.size
            self.assertLess(sizes["60"], sizes["90"])
            first = ficha.image.name

            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {**base, "record_image": png("b.png")})
            ficha.refresh_from_db()
            self.assertNotEqual(ficha.image.name, first)
            self.assertFalse(ficha.image.storage.exists(first))

            self.client.post(url, base)
            ficha.refresh_from_db()
            self.assertTrue(ficha.image)

            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {**base, "record_image-clear": "on"})
            ficha.refresh_from_db()
            self.assertFalse(ficha.image)

    def test_clearing_record_code_deletes_ficha_and_image_requires_code(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        Ficha.objects.create(
            enrollment=self.enrollment,
            campus=self.campus,
            date=self.enrollment.enrollment_date,
            code="8",
        )
        base = {
            "course": self.course.pk,
            "student": self.student.pk,
            "promoter": [],
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "40.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        url = reverse("enrollment-update", args=[self.enrollment.pk])
        response = self.client.post(
            url, {**base, "record_image": SimpleUploadedFile("x.png", b"x", "image/png")}
        )
        self.assertIn("record_image", response.context["form"].errors)
        self.assertEqual(self.client.post(url, {**base, "record_code": ""}).status_code, 302)
        self.assertFalse(Ficha.objects.filter(enrollment=self.enrollment).exists())

    def test_changing_enrollment_date_updates_ficha_date(self):
        ficha = Ficha.objects.create(
            enrollment=self.enrollment,
            campus=self.campus,
            date=self.enrollment.enrollment_date,
            code="9",
        )
        self.enrollment.enrollment_date = date(2026, 1, 5)
        self.enrollment.save()
        ficha.refresh_from_db()
        self.assertEqual(ficha.date, date(2026, 1, 5))

    def test_editing_enrollment_recalculates_installments(self):
        data = {
            "course": self.course.pk,
            "student": self.student.pk,
            "promoter": [],
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "40.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        url = reverse("enrollment-update", args=[self.enrollment.pk])
        due = self.enrollment.enrollment_date
        matricula = Installment.objects.create(
            enrollment=self.enrollment, concept="Matrícula", amount=30, due_date=due
        )
        monthly = Installment.objects.create(
            enrollment=self.enrollment,
            concept="Mensualidad inicial (2026-01)",
            amount=50,
            due_date=due,
        )

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        matricula.refresh_from_db()
        monthly.refresh_from_db()
        self.assertEqual(matricula.amount, 40)
        self.assertEqual(monthly.amount, 60)

    def test_fee_cannot_drop_below_amount_already_paid(self):
        data = {
            "course": self.course.pk,
            "student": self.student.pk,
            "promoter": [],
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "10.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        due = self.enrollment.enrollment_date
        matricula = Installment.objects.create(
            enrollment=self.enrollment, concept="Matrícula", amount=40, due_date=due
        )
        payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=User.objects.first(),
            receipt_number="900",
            amount=25,
        )
        PaymentAllocation.objects.create(payment=payment, installment=matricula, amount=25)

        response = self.client.post(reverse("enrollment-update", args=[self.enrollment.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("enrollment_fee"))
        matricula.refresh_from_db()
        self.assertEqual(matricula.amount, 40)

    def test_student_form_inputs_convert_names_to_uppercase(self):
        response = self.client.get(reverse("student-create"))

        self.assertContains(response, 'name="last_name"')
        self.assertContains(response, "<input", count=None)
        self.assertContains(response, 'data-uppercase style="text-transform:uppercase"', count=2)

    def test_student_creation_requires_separate_last_and_first_names(self):
        response = self.client.post(
            reverse("student-create"),
            {
                "last_name": "Pérez",
                "first_name": "Ana",
                "document_number": "12345678",
                "phone_numbers": "987654321",
                "active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        student = Student.objects.get(full_name="PÉREZ ANA")
        self.assertEqual(student.last_name, "PÉREZ")
        self.assertEqual(student.first_name, "ANA")

        invalid_response = self.client.post(
            reverse("student-create"),
            {
                "last_name": "",
                "first_name": "Ana",
                "phone_numbers": "987654321",
                "active": "on",
            },
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Este campo es obligatorio.")

    def test_student_names_are_unique_per_campus(self):
        other_campus = Campus.objects.create(name="Otra sede", active=True)
        same_name_at_other_campus = Student.objects.create(
            campus=other_campus,
            full_name=self.student.full_name,
            phone="987654321",
        )
        self.assertEqual(same_name_at_other_campus.full_name, self.student.full_name)

        duplicate_at_same_campus = Student(
            campus=self.campus,
            full_name=self.student.full_name,
            phone="987654321",
        )
        with self.assertRaises(ValidationError):
            duplicate_at_same_campus.full_clean()

    def test_only_unassigned_course_allows_repeated_enrollments(self):
        unassigned = Course.objects.get(campus=self.campus, name="POR ASIGNAR")
        for _ in range(2):
            Enrollment(
                campus=self.campus,
                student=self.student,
                course=unassigned,
                enrollment_fee=10,
                monthly_fee=10,
            ).full_clean()
            Enrollment.objects.create(campus=self.campus, student=self.student, course=unassigned)
        self.assertEqual(
            Enrollment.objects.filter(student=self.student, course=unassigned).count(), 2
        )
        response = self.client.get(reverse("enrollment-create"), {"student": self.student.pk})
        self.assertContains(response, f'<option value="{unassigned.pk}"')
        self.assertNotContains(response, f'<option value="{self.course.pk}"')
        with self.assertRaises(ValidationError):
            Enrollment(campus=self.campus, student=self.student, course=self.course).full_clean(
                exclude=["enrollment_fee", "monthly_fee"]
            )

    def test_default_promoters_cannot_be_combined_with_others(self):
        other = Promoter.objects.create(name="Otro Promotor")
        other.campuses.add(self.campus)
        particular, _ = Promoter.objects.get_or_create(name="PARTICULAR")
        particular.campuses.add(self.campus)
        base = {
            "course": self.course.pk,
            "student": self.student.pk,
            "enrollment_date": self.enrollment.enrollment_date.isoformat(),
            "enrollment_fee": "40.00",
            "monthly_fee": "60.00",
            "active": "on",
        }
        url = reverse("enrollment-update", args=[self.enrollment.pk])
        response = self.client.get(url)
        labels = [c[1] for c in response.context["form"].fields["promoter"].choices]
        self.assertEqual(labels[-2:], ["NN", "PARTICULAR"])
        self.assertEqual(labels[0], "OTRO PROMOTOR")
        response = self.client.post(url, {**base, "promoter": [particular.pk, other.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no se pueden combinar con otros promotores")
        response = self.client.post(url, {**base, "promoter": [particular.pk]})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(url, {**base, "promoter": [other.pk]})
        self.assertEqual(response.status_code, 302)

    def test_enrollment_create_lists_student_current_enrollments(self):
        response = self.client.get(reverse("enrollment-create"), {"student": self.student.pk})
        self.assertContains(response, "Cursos en los que ya está matriculado")
        self.assertContains(response, self.course.name)

        other = Student.objects.create(campus=self.campus, full_name="Sin matriculas")
        response = self.client.get(reverse("enrollment-create"), {"student": other.pk})
        self.assertNotContains(response, "Cursos en los que ya está matriculado")

    def test_record_code_cannot_repeat_on_same_enrollment_date(self):
        self.enrollment.enrollment_date = date(2026, 9, 29)
        self.enrollment.save()
        Ficha.objects.create(
            enrollment=self.enrollment,
            campus=self.campus,
            date=self.enrollment.enrollment_date,
            code="500",
        )
        other = Student.objects.create(campus=self.campus, full_name="Alumno ficha repetida")
        other_course = Course.objects.create(
            campus=self.campus, name="Otro curso", enrollment_fee=10, monthly_fee=10
        )
        data = {
            "course": other_course.pk,
            "student": other.pk,
            "record_code": "500",
            "promoter": [],
            "enrollment_date": "2026-09-29",
            "enrollment_fee": "10.00",
            "monthly_fee": "10.00",
            "active": "on",
        }
        url = reverse("enrollment-create") + f"?student={other.pk}"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("record_code", response.context["form"].errors)
        self.assertFalse(Enrollment.objects.filter(student=other).exists())
        data["enrollment_date"] = "2026-09-30"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertTrue(Enrollment.objects.filter(student=other).exists())

    def test_enrollment_form_defaults_to_unassigned_course_listed_first(self):
        unassigned = Course.objects.get(campus=self.campus, name="POR ASIGNAR")
        response = self.client.get(reverse("enrollment-create"), {"student": self.student.pk})
        form = response.context["form"]
        self.assertEqual(form.initial["course"], unassigned.pk)
        self.assertEqual(form.fields["course"].queryset.first(), unassigned)
        self.assertEqual(list(form.fields["course"].choices)[0][0].value, unassigned.pk)
        self.assertContains(response, 'data-unassigned="true"')

    def test_enrollment_in_unassigned_course_forces_zero_fees(self):
        unassigned = Course.objects.get(campus=self.campus, name="POR ASIGNAR")
        new_student = Student.objects.create(campus=self.campus, full_name="Alumno por asignar")
        response = self.client.get(
            reverse("enrollment-create"), {"student": new_student.pk, "course": unassigned.pk}
        )
        self.assertContains(response, 'data-unassigned="true"')
        self.assertContains(response, "readonly")
        response = self.client.post(
            reverse("enrollment-create") + f"?student={new_student.pk}",
            {
                "course": unassigned.pk,
                "student": new_student.pk,
                "promoter": [],
                "enrollment_date": "2026-09-29",
                "enrollment_fee": "99.00",
                "monthly_fee": "",
                "active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        enrollment = Enrollment.objects.get(student=new_student, course=unassigned)
        self.assertEqual(enrollment.enrollment_fee, 0)
        self.assertEqual(enrollment.monthly_fee, 0)
        self.assertFalse(Installment.objects.filter(enrollment=enrollment).exists())

    def test_enrollment_creation_saves_user_selected_date(self):
        new_student = Student.objects.create(
            campus=self.campus,
            full_name="Alumno con fecha elegida",
        )
        response = self.client.get(reverse("enrollment-create"))
        self.assertContains(response, "selecciona un estudiante")
        self.assertContains(response, new_student.full_name)
        self.assertContains(response, 'id="student-search"')
        filtered = self.client.get(reverse("enrollment-create"), {"q": "fecha elegida"})
        self.assertContains(filtered, new_student.full_name)
        self.assertNotContains(filtered, self.student.full_name)
        response = self.client.get(reverse("enrollment-create"), {"student": new_student.pk})
        self.assertContains(response, 'type="date"')
        self.assertContains(response, f'value="{timezone.localdate():%Y-%m-%d}"')
        response = self.client.post(
            reverse("enrollment-create"),
            {
                "course": self.course.pk,
                "student": new_student.pk,
                "record_code": "202602",
                "promoter": [],
                "enrollment_date": "2026-09-29",
                "enrollment_fee": "25.00",
                "monthly_fee": "35.00",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        created_enrollment = Enrollment.objects.get(student=new_student, course=self.course)
        self.assertEqual(created_enrollment.enrollment_date, date(2026, 9, 29))
        self.assertContains(response, "29/09/2026")

    def test_search_ignores_accents_and_case(self):
        Student.objects.create(campus=self.campus, full_name="Canción Ñandú")
        for term in ("cancion", "CANCIÓN", "CANcion", "nandu"):
            response = self.client.get(reverse("student-list"), {"q": term})
            self.assertContains(response, "CANCIÓN ÑANDÚ", msg_prefix=term)

    def test_list_pages_use_live_filtering(self):
        for name in (
            "student-list",
            "enrollment-list",
            "course-student-tables",
            "payment-list",
            "pending-debts",
            "payment-create",
        ):
            response = self.client.get(reverse(name))
            self.assertContains(response, "data-live-filter", msg_prefix=name)
            self.assertContains(response, "data-live-region", msg_prefix=name)

    def test_enrollment_edit_preserves_custom_fees_instead_of_course_fees(self):
        self.enrollment.enrollment_fee = 25
        self.enrollment.monthly_fee = 55
        self.enrollment.save(update_fields=["enrollment_fee", "monthly_fee"])

        response = self.client.get(reverse("enrollment-update", args=[self.enrollment.pk]))

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(str(form["enrollment_fee"].value()), "25.00")
        self.assertEqual(str(form["monthly_fee"].value()), "55.00")
        self.assertNotContains(response, "updateCourseFees();")

    def test_enrollment_can_have_multiple_promoters(self):
        first_promoter = Promoter.objects.create(name="Primer promotor", active=True)
        second_promoter = Promoter.objects.create(name="Segundo promotor", active=True)
        response = self.client.get(reverse("enrollment-update", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "PRIMER PROMOTOR")
        self.assertContains(response, "SEGUNDO PROMOTOR")
        response = self.client.post(
            reverse("enrollment-update", args=[self.enrollment.pk]),
            {
                "course": self.course.pk,
                "student": self.student.pk,
                "record_code": "202603",
                "promoter": [first_promoter.pk, second_promoter.pk],
                "enrollment_date": self.enrollment.enrollment_date.isoformat(),
                "enrollment_fee": "40.00",
                "monthly_fee": "60.00",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            set(self.enrollment.promoter.values_list("pk", flat=True)),
            {first_promoter.pk, second_promoter.pk},
        )

    def test_deleting_student_deactivates_records_and_voids_receipt(self):
        installment, payment, allocation = self.add_payment_history()
        response = self.client.get(reverse("student-delete", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("student-delete", args=[self.student.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()
        installment.refresh_from_db()
        payment.refresh_from_db()
        self.assertFalse(self.student.active)
        self.assertFalse(self.enrollment.active)
        self.assertFalse(installment.active)
        self.assertEqual(payment.status, Payment.Status.VOID)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(PaymentAllocation.objects.filter(pk=allocation.pk).exists())

    def test_deleting_enrollment_deactivates_and_preserves_history(self):
        installment, payment, allocation = self.add_payment_history()
        response = self.client.get(reverse("enrollment-delete", args=[self.enrollment.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("enrollment-delete", args=[self.enrollment.pk]), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.enrollment.refresh_from_db()
        installment.refresh_from_db()
        payment.refresh_from_db()
        self.assertFalse(self.enrollment.active)
        self.assertFalse(installment.active)
        self.assertEqual(payment.status, Payment.Status.VOID)
        self.assertTrue(PaymentAllocation.objects.filter(pk=allocation.pk).exists())

    def test_student_and_enrollment_lists_link_to_payment_form(self):
        Installment.objects.create(
            enrollment=self.enrollment,
            concept="Saldo pendiente",
            amount=100,
            due_date=date(2026, 10, 14),
        )
        response = self.client.get(reverse("student-list"))
        self.assertContains(
            response,
            f'href="{reverse("payment-create")}?student={self.student.pk}"',
        )
        self.assertContains(response, 'aria-label="Editar estudiante"')
        self.assertContains(response, 'aria-label="Dar de baja estudiante"')
        response = self.client.get(reverse("enrollment-list"))
        self.assertContains(
            response,
            f'href="{reverse("payment-create")}?enrollment={self.enrollment.pk}"',
        )
        self.assertContains(response, 'aria-label="Pagar matrícula"')
        self.assertContains(response, 'aria-label="Editar matrícula"')
        self.assertContains(response, 'aria-label="Dar de baja matrícula"')
        response = self.client.get(reverse("payment-create"), {"student": self.student.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e.pk for e in response.context["enrollments"]], [self.enrollment.pk])

    def test_student_list_shows_active_enrollment_count_and_highlights_zero(self):
        student_without_enrollments = Student.objects.create(
            campus=self.campus,
            full_name="Estudiante sin matrícula",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=student_without_enrollments,
            course=self.course,
            active=False,
        )

        response = self.client.get(reverse("student-list"))
        students = {student.pk: student for student in response.context["students"]}

        self.assertEqual(students[self.student.pk].enrollment_count, 1)
        self.assertEqual(students[student_without_enrollments.pk].enrollment_count, 0)
        self.assertEqual(students[self.student.pk].row_number, 1)
        self.assertContains(response, "Cursos matriculados")
        self.assertContains(response, ">N.º ↓</a>")
        self.assertContains(response, "chip red darken-1")
        self.assertNotContains(response, "<th>Sede</th>")

        by_name = self.client.get(reverse("student-list"), {"sort": "name", "direction": "desc"})
        self.assertEqual(by_name.context["students"][0].pk, student_without_enrollments.pk)
        by_enrollments = self.client.get(
            reverse("student-list"), {"sort": "enrollments", "direction": "desc"}
        )
        self.assertEqual(by_enrollments.context["students"][0].pk, self.student.pk)
        by_row_number = self.client.get(
            reverse("student-list"), {"sort": "row_number", "direction": "desc"}
        )
        self.assertEqual(by_row_number.context["students"][0].pk, student_without_enrollments.pk)
        self.assertContains(response, "?sort=row_number&amp;direction=asc")

    def test_student_name_links_to_only_that_students_enrollments(self):
        other_student = Student.objects.create(
            campus=self.campus,
            full_name="Otra alumna",
        )
        other_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=self.course,
        )

        response = self.client.get(reverse("enrollment-list"))
        self.assertContains(
            response,
            f'href="{reverse("student-enrollment-list", args=[self.student.pk])}">{self.student.full_name}</a>',
        )

        response = self.client.get(reverse("student-enrollment-list", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="student" value="{self.student.full_name}"')
        self.assertEqual(
            {enrollment.pk for enrollment in response.context["enrollments"]},
            {self.enrollment.pk},
        )
        self.assertNotIn(
            other_enrollment.pk, {enrollment.pk for enrollment in response.context["enrollments"]}
        )

    def test_course_promoter_and_enrollment_date_links_filter_exactly(self):
        promoter = Promoter.objects.create(name="Promotor seleccionado", active=True)
        self.enrollment.enrollment_date = date(2026, 9, 29)
        self.enrollment.save(update_fields=["enrollment_date"])
        self.enrollment.promoter.add(promoter)
        other_student = Student.objects.create(campus=self.campus, full_name="Otra estudiante")
        other_course = Course.objects.create(
            campus=self.campus,
            name=self.course.name,
            schedule="Miércoles",
            group="B",
        )
        other_promoter = Promoter.objects.create(name="Otro promotor", active=True)
        other_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=other_course,
            enrollment_date=date(2026, 10, 1),
        )
        other_enrollment.promoter.add(other_promoter)

        response = self.client.get(reverse("enrollment-list"))
        self.assertContains(response, f"?course_id={self.course.pk}")
        self.assertContains(response, f"?promoter_id={promoter.pk}")
        self.assertContains(response, "?enrollment_date=2026-09-29")

        filters = [
            ({"course_id": self.course.pk}, "course", self.course.name),
            ({"promoter_id": promoter.pk}, "promoter", promoter.name),
            ({"enrollment_date": "2026-09-29"}, "enrollment_date_from", "2026-09-29"),
        ]
        for query, input_name, expected_value in filters:
            with self.subTest(query=query):
                response = self.client.get(reverse("enrollment-list"), query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {enrollment.pk for enrollment in response.context["enrollments"]},
                    {self.enrollment.pk},
                )
                self.assertContains(response, f'name="{input_name}" value="{expected_value}"')
                if "enrollment_date" in query:
                    self.assertContains(response, 'name="enrollment_date_to" value="2026-09-29"')

    def test_enrollment_list_shows_costs_and_outstanding_debt(self):
        self.add_payment_history()
        Installment.objects.create(
            enrollment=self.enrollment,
            concept="Cuota adicional",
            amount=30,
            due_date=date(2026, 11, 14),
        )

        response = self.client.get(reverse("enrollment-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Costo de inscripción")
        self.assertContains(response, "Mensualidad")
        self.assertContains(response, "Pago total")
        self.assertContains(response, "Pagado")
        self.assertContains(response, "Deuda")
        self.assertContains(response, "S/ 40,00")
        self.assertContains(response, "S/ 60,00")
        self.assertContains(response, "S/ 90,00")
        listed_enrollment = response.context["enrollments"][0]
        self.assertEqual(str(listed_enrollment.total_enrollment_cost), "100.00")
        self.assertEqual(str(listed_enrollment.total_paid), "40.00")
        self.assertEqual(str(listed_enrollment.total_debt), "90.00")

    def test_enrollment_excel_export_returns_workbook_and_respects_filters(self):
        other_student = Student.objects.create(
            campus=self.campus,
            full_name="Otro estudiante para exportar",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=self.course,
        )
        response = self.client.get(
            reverse("enrollment-excel"),
            {"student": self.student.full_name},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(response.content.startswith(b"PK"))
        self.assertIn(
            b'attachment; filename="matriculas_', response["Content-Disposition"].encode()
        )
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        worksheet = workbook["Matrículas"]
        rows = list(worksheet.iter_rows(values_only=True))
        self.assertIn("ESTUDIANTE DE PRUEBA", [value for row in rows for value in row])
        self.assertNotIn("OTRO ESTUDIANTE PARA EXPORTAR", [value for row in rows for value in row])
        self.assertEqual(rows[3][0], "N.º")
        self.assertNotIn("Estado", rows[3])
        self.assertEqual(rows[4][0], 1)

    def test_enrollment_excel_export_excludes_inactive_enrollments(self):
        inactive_student = Student.objects.create(
            campus=self.campus,
            full_name="Estudiante con matrícula inactiva",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=inactive_student,
            course=self.course,
            active=False,
        )

        response = self.client.get(reverse("enrollment-excel"))

        workbook = load_workbook(BytesIO(response.content), data_only=True)
        worksheet = workbook["Matrículas"]
        exported_values = [value for row in worksheet.iter_rows(values_only=True) for value in row]
        self.assertIn(self.student.full_name, exported_values)
        self.assertNotIn(inactive_student.full_name, exported_values)

    def test_enrollment_excel_export_orders_rows_by_student_name(self):
        first_student = Student.objects.create(
            campus=self.campus,
            full_name="Ana Alumna",
        )
        last_student = Student.objects.create(
            campus=self.campus,
            full_name="Zoe Alumna",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=first_student,
            course=self.course,
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=last_student,
            course=self.course,
        )

        response = self.client.get(reverse("enrollment-excel"))

        workbook = load_workbook(BytesIO(response.content), data_only=True)
        worksheet = workbook["Matrículas"]
        rows = list(worksheet.iter_rows(min_row=5, values_only=True))
        self.assertEqual(
            [row[1] for row in rows],
            ["ANA ALUMNA", "ESTUDIANTE DE PRUEBA", "ZOE ALUMNA"],
        )
        self.assertEqual([row[0] for row in rows], [1, 2, 3])

    def test_enrollment_excel_export_uses_debt_status_row_colors(self):
        Installment.objects.create(
            enrollment=self.enrollment,
            concept="Cuota pendiente",
            amount=100,
            due_date=date(2026, 10, 14),
        )
        no_debt_student = Student.objects.create(
            campus=self.campus,
            full_name="Alumno sin deuda",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=no_debt_student,
            course=self.course,
        )

        response = self.client.get(reverse("enrollment-excel"))

        workbook = load_workbook(BytesIO(response.content), data_only=True)
        worksheet = workbook["Matrículas"]
        rows_by_student = {row[1].value: row for row in worksheet.iter_rows(min_row=5)}
        self.assertTrue(
            rows_by_student[self.student.full_name][0].fill.fgColor.rgb.endswith("FFF3CD")
        )
        self.assertTrue(
            rows_by_student[no_debt_student.full_name][0].fill.fgColor.rgb.endswith("D1E7DD")
        )

    def test_enrollment_row_numbers_follow_oldest_enrollment_date(self):
        self.enrollment.enrollment_date = date(2026, 9, 15)
        self.enrollment.save(update_fields=["enrollment_date"])
        older_student = Student.objects.create(
            campus=self.campus,
            full_name="Inscripción más antigua",
        )
        older_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=older_student,
            course=self.course,
            enrollment_date=date(2026, 8, 1),
        )

        response = self.client.get(
            reverse("enrollment-list"),
            {"sort": "student", "direction": "desc"},
        )
        self.assertContains(response, "N.º")
        self.assertContains(response, "?sort=row_number&amp;direction=asc")
        ranks = {
            enrollment.pk: enrollment.row_number for enrollment in response.context["enrollments"]
        }
        self.assertEqual(ranks[older_enrollment.pk], 1)
        self.assertEqual(ranks[self.enrollment.pk], 2)

        ascending = self.client.get(
            reverse("enrollment-list"),
            {"sort": "row_number", "direction": "asc"},
        )
        descending = self.client.get(
            reverse("enrollment-list"),
            {"sort": "row_number", "direction": "desc"},
        )
        self.assertEqual(ascending.context["enrollments"][0].pk, older_enrollment.pk)
        self.assertEqual(descending.context["enrollments"][0].pk, self.enrollment.pk)

        response = self.client.get(reverse("enrollment-excel"))
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        worksheet = workbook["Matrículas"]
        ranks_by_student = {
            row[1]: row[0] for row in worksheet.iter_rows(min_row=5, values_only=True)
        }
        self.assertEqual(ranks_by_student[self.student.full_name], 1)
        self.assertEqual(ranks_by_student["INSCRIPCIÓN MÁS ANTIGUA"], 2)

    def test_enrollment_filters_cover_student_course_record_code_and_promoter(self):
        promoter = Promoter.objects.create(name="Promotor de prueba", active=True)
        Ficha.objects.create(
            enrollment=self.enrollment,
            campus=self.campus,
            date=self.enrollment.enrollment_date,
            code="42",
        )
        self.enrollment.promoter.add(promoter)

        filters = {
            "student": "Estudiante de",
            "course": "Curso de",
            "record_code": "4",
            "promoter": "Promotor de",
        }
        for field, value in filters.items():
            with self.subTest(field=field):
                response = self.client.get(reverse("enrollment-list"), {field: value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["enrollments"]), 1)
                self.assertEqual(response.context["enrollments"][0].pk, self.enrollment.pk)

    def test_record_code_check_lists_missing_codes_for_the_selected_date(self):
        check_date = date(2026, 10, 14)
        for record_code in ["1", "2", "4", "5"]:
            student = Student.objects.create(
                campus=self.campus,
                full_name=f"Alumno de ficha {record_code}",
            )
            enrollment = Enrollment.objects.create(
                campus=self.campus,
                student=student,
                course=self.course,
                enrollment_date=check_date,
            )
            Ficha.objects.create(
                enrollment=enrollment, campus=self.campus, date=check_date, code=record_code
            )
        other_date_student = Student.objects.create(
            campus=self.campus,
            full_name="Alumno de otra fecha",
        )
        other_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_date_student,
            course=self.course,
            enrollment_date=date(2026, 10, 15),
        )
        Ficha.objects.create(
            enrollment=other_enrollment, campus=self.campus, date=date(2026, 10, 15), code="3"
        )

        response = self.client.get(
            reverse("tools"),
            {
                "record_code_check_date": check_date.isoformat(),
                "record_code_start": "1",
                "record_code_end": "10",
                "check_record_codes": "1",
            },
        )

        self.assertEqual(
            response.context["missing_record_codes"],
            [3, 6, 7, 8, 9, 10],
        )
        self.assertEqual(response.context["missing_record_codes"], [3, 6, 7, 8, 9, 10])
        self.assertContains(response, '<span class="tool-chip">10</span>')

    def test_enrollment_rows_highlight_debt_and_no_debt(self):
        Installment.objects.create(
            enrollment=self.enrollment,
            concept="Pendiente",
            amount=100,
            due_date=date(2026, 10, 14),
        )
        other_student = Student.objects.create(campus=self.campus, full_name="Otro estudiante")
        paid_course = Course.objects.create(
            campus=self.campus,
            name="Curso pagado",
            start_date=date(2026, 10, 14),
        )
        paid_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=paid_course,
            active=True,
        )
        paid_installment = Installment.objects.create(
            enrollment=paid_enrollment,
            concept="Pagado",
            amount=50,
            due_date=date(2026, 10, 14),
        )
        paid_payment = Payment.objects.create(
            campus=self.campus,
            enrollment=paid_enrollment,
            cashier=self.user,
            receipt_number="COLOR-001",
            amount=50,
        )
        PaymentAllocation.objects.create(
            payment=paid_payment,
            installment=paid_installment,
            amount=50,
        )

        response = self.client.get(reverse("enrollment-list"))

        self.assertContains(response, "debt-owed")
        self.assertContains(response, "debt-clear")
        self.assertNotContains(response, "row-warning")
        self.assertNotContains(response, "row-success")
        self.assertNotContains(response, "<th>Sede</th>")

    def test_enrollment_list_filters_by_debt_status(self):
        Installment.objects.create(
            enrollment=self.enrollment,
            concept="Pendiente",
            amount=100,
            due_date=date(2026, 10, 14),
        )
        no_debt_student = Student.objects.create(
            campus=self.campus,
            full_name="Estudiante sin deuda",
        )
        no_debt_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=no_debt_student,
            course=self.course,
        )

        with_debt = self.client.get(reverse("enrollment-list"), {"debt_status": "with_debt"})
        without_debt = self.client.get(reverse("enrollment-list"), {"debt_status": "without_debt"})

        self.assertEqual(
            {enrollment.pk for enrollment in with_debt.context["enrollments"]},
            {self.enrollment.pk},
        )
        self.assertEqual(
            {enrollment.pk for enrollment in without_debt.context["enrollments"]},
            {no_debt_enrollment.pk},
        )
        self.assertContains(with_debt, 'value="with_debt" selected')
        self.assertContains(without_debt, 'value="without_debt" selected')

    def test_enrollment_list_filters_by_date_range(self):
        older_student = Student.objects.create(campus=self.campus, full_name="Matrícula anterior")
        older_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=older_student,
            course=self.course,
            enrollment_date=date(2026, 10, 1),
        )

        response = self.client.get(
            reverse("enrollment-list"),
            {"enrollment_date_from": "2026-10-10"},
        )
        self.assertEqual(
            {enrollment.pk for enrollment in response.context["enrollments"]},
            {self.enrollment.pk},
        )
        self.assertContains(response, "Fecha de matrícula - Desde")
        self.assertContains(response, "Fecha de matrícula - Hasta")

        response = self.client.get(
            reverse("enrollment-list"),
            {"enrollment_date_to": "2026-10-10"},
        )
        self.assertEqual(
            {enrollment.pk for enrollment in response.context["enrollments"]},
            {older_enrollment.pk},
        )

    def test_enrollment_table_sorts_by_student_and_outstanding_debt(self):
        other_student = Student.objects.create(campus=self.campus, full_name="Zeta Estudiante")
        other_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=self.course,
        )

        response = self.client.get(
            reverse("enrollment-list"),
            {"sort": "student", "direction": "desc"},
        )
        self.assertEqual(response.context["enrollments"][0].pk, other_enrollment.pk)
        self.assertContains(response, "?sort=student&amp;direction=asc")

        self.add_payment_history()
        Installment.objects.create(
            enrollment=other_enrollment,
            concept="Deuda menor",
            amount=30,
            due_date=date(2026, 10, 14),
        )
        response = self.client.get(
            reverse("enrollment-list"),
            {"sort": "total_debt", "direction": "desc"},
        )
        self.assertEqual(response.context["enrollments"][0].pk, self.enrollment.pk)

    def test_enrollment_filters_are_preserved_in_pagination(self):
        for index in range(26):
            student = Student.objects.create(
                campus=self.campus,
                full_name=f"Alumno paginado {index}",
            )
            enrollment = Enrollment.objects.create(
                campus=self.campus,
                student=student,
                course=self.course,
            )
            Ficha.objects.create(
                enrollment=enrollment,
                campus=self.campus,
                date=enrollment.enrollment_date,
                code=f"999{index}",
            )

        response = self.client.get(reverse("enrollment-list"), {"record_code": "999"})

        self.assertTrue(response.context["is_paginated"])
        self.assertContains(response, "?record_code=999&amp;page=2")

    def test_enrollment_list_shows_associated_receipt_numbers_and_void_status(self):
        confirmed_payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="RECIBO-ACTIVO-01",
            amount=20,
        )
        void_payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="RECIBO-ANULADO-02",
            amount=15,
            status=Payment.Status.VOID,
        )

        response = self.client.get(reverse("enrollment-list"))

        self.assertContains(response, "Recibos")
        self.assertContains(response, "RECIBO-ACTIVO-01")
        self.assertContains(response, "RECIBO-ANULADO-02")
        self.assertContains(response, "Anulado")
        self.assertContains(
            response,
            f'href="{reverse("payment-receipt", args=[confirmed_payment.pk])}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("payment-receipt", args=[void_payment.pk])}"',
        )
        self.assertEqual(
            self.client.get(reverse("payment-receipt", args=[void_payment.pk])).status_code,
            200,
        )

    def test_student_form_accepts_multiple_phones_and_labels_document_as_dni(self):
        response = self.client.get(reverse("student-update", args=[self.student.pk]))
        self.assertContains(response, "DNI")
        self.assertContains(response, "Teléfonos")
        form_data = QueryDict(mutable=True)
        form_data.update(
            {
                "last_name": "Estudiante de",
                "first_name": "prueba",
                "document_number": self.student.document_number,
                "active": "on",
            }
        )
        form_data.setlist("phone_numbers", ["987654321", "912345678"])
        self.assertEqual(
            PhoneListWidget().value_from_datadict(form_data, None, "phone_numbers"),
            "987654321, 912345678",
        )
        response = self.client.post(
            reverse("student-update", args=[self.student.pk]),
            {
                "last_name": "Estudiante de",
                "first_name": "prueba",
                "document_number": self.student.document_number,
                "phone_numbers": "987654321, 912345678",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "987654321, 912345678")

    def test_student_form_requires_at_least_one_phone(self):
        response = self.client.post(
            reverse("student-update", args=[self.student.pk]),
            {
                "last_name": "Estudiante de",
                "first_name": "prueba",
                "document_number": self.student.document_number,
                "phone_numbers": "",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo es obligatorio.")
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "987654321")

    def test_student_form_rejects_any_invalid_phone(self):
        response = self.client.post(
            reverse("student-update", args=[self.student.pk]),
            {
                "last_name": "Estudiante de",
                "first_name": "prueba",
                "document_number": self.student.document_number,
                "phone_numbers": "987654321, 123456789",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no es válido")
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "987654321")


class UnassignedCourseTests(TestCase):
    def test_course_and_enrollment_fees_must_be_greater_than_zero(self):
        campus = Campus.objects.create(name="Sede Montos")
        course = Course(campus=campus, name="X", schedule="Y", enrollment_fee=0, monthly_fee=-5)
        with self.assertRaises(ValidationError) as context:
            course.full_clean()
        self.assertIn("enrollment_fee", context.exception.message_dict)
        self.assertIn("monthly_fee", context.exception.message_dict)
        enrollment = Enrollment(enrollment_fee=0, monthly_fee=0)
        with self.assertRaises(ValidationError) as context:
            enrollment.full_clean()
        self.assertIn("enrollment_fee", context.exception.message_dict)
        self.assertIn("monthly_fee", context.exception.message_dict)

    def test_new_campus_gets_default_promoters(self):
        campus = Campus.objects.create(name="Sede Promotores")
        names = set(campus.promoters.values_list("name", flat=True))
        self.assertEqual(names, {"PARTICULAR", "NN"})
        other = Campus.objects.create(name="Otra Sede Promotores")
        self.assertEqual(Promoter.objects.filter(name="NN").count(), 1)
        self.assertTrue(other.promoters.filter(name="NN").exists())

    def test_new_campus_gets_unassigned_course_and_schedule(self):
        campus = Campus.objects.create(name="Sede Nueva")
        course = Course.objects.get(campus=campus, name="POR ASIGNAR")
        self.assertEqual(course.schedule, "PENDIENTE DE ASIGNACION")
        self.assertEqual(course.group, "PENDIENTE DE ASIGNACION")
        self.assertIsNone(course.start_date)
        self.assertEqual(course.start_date_display(), "PENDIENTE DE ASIGNACION")
        for field in ("capacity", "enrollment_fee", "monthly_fee"):
            self.assertIsNone(getattr(course, field))
        self.assertEqual(course.capacity_display(), "PENDIENTE DE ASIGNACION")
        self.assertEqual(course.enrollment_fee_display(), "PENDIENTE DE ASIGNACION")
        self.assertEqual(course.monthly_fee_display(), "PENDIENTE DE ASIGNACION")
        regular = Course(
            campus=campus,
            name="X",
            schedule="Y",
            group="1",
            start_date=None,
            capacity=None,
            enrollment_fee=None,
            monthly_fee=None,
        )
        with self.assertRaises(ValidationError) as context:
            regular.full_clean()
        for field in ("start_date", "capacity", "enrollment_fee", "monthly_fee"):
            self.assertIn(field, context.exception.message_dict)
        self.assertTrue(
            Schedule.objects.filter(campus=campus, name="PENDIENTE DE ASIGNACION").exists()
        )

    def test_only_superuser_can_modify_unassigned_course(self):
        from django.contrib.admin.sites import site
        from django.contrib.auth.models import Permission
        from django.test import RequestFactory

        campus = Campus.objects.create(name="Sede Admin")
        course = Course.objects.get(campus=campus, name="POR ASIGNAR")
        schedule = Schedule.objects.get(campus=campus, name="PENDIENTE DE ASIGNACION")
        staff = User.objects.create_user("staff", password="x", is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label="students"))
        admin_user = User.objects.create_superuser("root", password="x")
        request = RequestFactory().get("/")
        for obj in (course, schedule):
            model_admin = site._registry[type(obj)]
            request.user = User.objects.get(pk=staff.pk)
            self.assertFalse(model_admin.has_change_permission(request, obj))
            self.assertFalse(model_admin.has_delete_permission(request, obj))
            request.user = admin_user
            self.assertTrue(model_admin.has_change_permission(request, obj))


class CourseUniquenessTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede de cursos", active=True)
        self.course_data = {
            "campus": self.campus,
            "name": "Matemáticas",
            "schedule": "Lunes 18:00",
            "group": "A",
        }

    def test_course_group_must_be_positive_integer_except_unassigned(self):
        for bad in ("A", "0", "-1", "1.5", ""):
            with self.assertRaises(ValidationError, msg=bad) as context:
                Course(**{**self.course_data, "group": bad}).full_clean()
            self.assertIn("group", context.exception.message_dict)
        fees = {"enrollment_fee": 10, "monthly_fee": 10}
        Course(**{**self.course_data, "group": "2", **fees}).full_clean()
        Course.objects.get(campus=self.campus, name="POR ASIGNAR").full_clean(
            exclude=["enrollment_fee", "monthly_fee"]
        )

    def test_same_course_identity_cannot_be_created_twice_in_one_campus(self):
        Course.objects.create(**self.course_data)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Course.objects.create(**self.course_data)

    def test_same_course_identity_is_allowed_in_another_campus(self):
        Course.objects.create(**self.course_data)
        other_campus = Campus.objects.create(name="Otra sede", active=True)
        Course.objects.create(**{**self.course_data, "campus": other_campus})

    def test_course_requires_schedule_and_defaults_group_to_one(self):
        course = Course(campus=self.campus, name="Curso sin horario")

        with self.assertRaises(ValidationError) as context:
            course.full_clean()

        self.assertIn("schedule", context.exception.message_dict)
        self.assertEqual(course.group, "1")

    def test_default_schedules_are_available_in_the_catalog(self):
        self.assertEqual(
            set(Schedule.objects.filter(campus=self.campus).values_list("name", flat=True)),
            {"SÁBADOS DE 8AM A 11AM", "SÁBADOS DE 11AM A 2PM", "PENDIENTE DE ASIGNACION"},
        )
