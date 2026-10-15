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
from students.models import Course, Enrollment, Promoter, Schedule, Student


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
        self.assertEqual(workbook.sheetnames, ["Historia", "Matemáticas"])
        self.assertNotIn("Física", workbook.sheetnames)
        math_rows = list(workbook["Matemáticas"].iter_rows(values_only=True))
        history_rows = list(workbook["Historia"].iter_rows(values_only=True))
        self.assertEqual(len(workbook["Matemáticas"].tables), 5)
        self.assertEqual(len(workbook["Historia"].tables), 1)
        self.assertIn("Ana Pérez", [value for row in math_rows for value in row])
        self.assertIn("Luis Gómez", [value for row in math_rows for value in row])
        math_values = [value for row in math_rows for value in row]
        for group in ("A", "B", "C", "D", "E"):
            self.assertTrue(
                any(
                    isinstance(value, str) and value.startswith(f"Grupo: {group} ·")
                    for value in math_values
                )
            )
        self.assertIn("Marta Ruiz", [value for row in history_rows for value in row])
        math_table = workbook["Matemáticas"].tables[f"Course_{self.course_a.pk}"]
        header_row = int(math_table.ref.split(":")[0][1:])
        self.assertEqual(
            [workbook["Matemáticas"].cell(header_row, column).value for column in range(1, 6)],
            ["N.º", "Alumno", "DNI", "Teléfonos", "Fecha de matrícula"],
        )
        self.assertEqual(workbook["Matemáticas"].cell(header_row + 1, 1).value, 1)
        self.assertEqual(workbook["Matemáticas"].cell(header_row + 2, 1).value, 2)


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
        self.assertEqual(self.student.full_name, "Apellidos actualizados Nombres")

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
        self.assertEqual(self.enrollment.record_code, "202601")

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
        student = Student.objects.get(full_name="Pérez Ana")
        self.assertEqual(student.last_name, "Pérez")
        self.assertEqual(student.first_name, "Ana")

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
            self.assertContains(response, "Canción Ñandú", msg_prefix=term)

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
        self.assertContains(response, "Primer promotor")
        self.assertContains(response, "Segundo promotor")
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
        self.assertEqual(
            str(response.context["form"]["enrollment"].value()),
            str(self.enrollment.pk),
        )

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
        self.assertIn("Estudiante de prueba", [value for row in rows for value in row])
        self.assertNotIn("Otro estudiante para exportar", [value for row in rows for value in row])
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
            ["Ana Alumna", "Estudiante de prueba", "Zoe Alumna"],
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
        self.assertEqual(ranks_by_student["Inscripción más antigua"], 2)

    def test_enrollment_filters_cover_student_course_record_code_and_promoter(self):
        promoter = Promoter.objects.create(name="Promotor de prueba", active=True)
        self.enrollment.record_code = "42"
        self.enrollment.record_code = "42"
        self.enrollment.save(update_fields=["record_code"])
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
            Enrollment.objects.create(
                campus=self.campus,
                student=student,
                course=self.course,
                record_code=record_code,
                enrollment_date=check_date,
            )
        other_date_student = Student.objects.create(
            campus=self.campus,
            full_name="Alumno de otra fecha",
        )
        Enrollment.objects.create(
            campus=self.campus,
            student=other_date_student,
            course=self.course,
            record_code="3",
            enrollment_date=date(2026, 10, 15),
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
            ["3", "6", "7", "8", "9", "10"],
        )
        self.assertContains(response, "3, 6, 7, 8, 9, 10")

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

        self.assertContains(response, "row-warning")
        self.assertContains(response, "row-success")
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
            Enrollment.objects.create(
                campus=self.campus,
                student=student,
                course=self.course,
                record_code="999",
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


class CourseUniquenessTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede de cursos", active=True)
        self.course_data = {
            "campus": self.campus,
            "name": "Matemáticas",
            "schedule": "Lunes 18:00",
            "group": "A",
        }

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
            set(Schedule.objects.values_list("name", flat=True)),
            {"SÁBADOS DE 8AM A 11AM", "SÁBADOS DE 11AM A 2PM"},
        )
