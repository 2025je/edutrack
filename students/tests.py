from datetime import date
from io import BytesIO

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from core.models import Campus, User
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Course, Enrollment, Promoter, Student


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
				any(isinstance(value, str) and value.startswith(f"Grupo: {group} ·") for value in math_values)
			)
		self.assertIn("Marta Ruiz", [value for row in history_rows for value in row])
		math_table = workbook["Matemáticas"].tables[f"Course_{self.course_a.pk}"]
		header_row = int(math_table.ref.split(":")[0][1:])
		self.assertEqual(
			[workbook["Matemáticas"].cell(header_row, column).value for column in range(1, 6)],
			["N.º fila", "Alumno", "DNI", "Teléfonos", "Fecha de matrícula"],
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
				"full_name": "Estudiante actualizado",
				"document_number": self.student.document_number,
				"phone": self.student.phone,
				"active": "on",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.student.refresh_from_db()
		self.assertEqual(self.student.full_name, "Estudiante actualizado")

		response = self.client.get(reverse("enrollment-update", args=[self.enrollment.pk]))
		self.assertEqual(response.status_code, 200)
		response = self.client.post(
			reverse("enrollment-update", args=[self.enrollment.pk]),
			{
				"course": self.course.pk,
				"student": self.student.pk,
				"record_code": "F-2026-01",
				"promoter": "",
				"enrollment_fee": "40.00",
				"monthly_fee": "60.00",
				"active": "on",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.enrollment.refresh_from_db()
		self.assertEqual(self.enrollment.record_code, "F-2026-01")

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
		response = self.client.post(reverse("enrollment-delete", args=[self.enrollment.pk]), follow=True)
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
			f'href="{reverse("payment-create")}?student={self.student.pk}">Pagar</a>',
		)
		response = self.client.get(reverse("enrollment-list"))
		self.assertContains(
			response,
			f'href="{reverse("payment-create")}?enrollment={self.enrollment.pk}">Pagar</a>',
		)
		response = self.client.get(reverse("payment-create"), {"student": self.student.pk})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			str(response.context["form"]["enrollment"].value()),
			str(self.enrollment.pk),
		)

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

	def test_enrollment_filters_cover_student_course_record_code_and_promoter(self):
		promoter = Promoter.objects.create(name="Promotor de prueba", active=True)
		self.enrollment.record_code = "FICHA-42"
		self.enrollment.promoter = promoter
		self.enrollment.save(update_fields=["record_code", "promoter"])

		filters = {
			"student": "Estudiante de",
			"course": "Curso de",
			"record_code": "FICHA-4",
			"promoter": "Promotor de",
		}
		for field, value in filters.items():
			with self.subTest(field=field):
				response = self.client.get(reverse("enrollment-list"), {field: value})
				self.assertEqual(response.status_code, 200)
				self.assertEqual(len(response.context["enrollments"]), 1)
				self.assertEqual(response.context["enrollments"][0].pk, self.enrollment.pk)

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

		self.assertContains(response, "table-warning")
		self.assertContains(response, "table-success")
		self.assertNotContains(response, "<th>Sede</th>")

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
				record_code="PAGINADO",
			)

		response = self.client.get(reverse("enrollment-list"), {"record_code": "PAGINADO"})

		self.assertTrue(response.context["is_paginated"])
		self.assertContains(response, "?record_code=PAGINADO&amp;page=2")

	def test_student_form_accepts_multiple_phones_and_labels_document_as_dni(self):
		response = self.client.get(reverse("student-update", args=[self.student.pk]))
		self.assertContains(response, "DNI")
		self.assertContains(response, "Teléfonos")
		response = self.client.post(
			reverse("student-update", args=[self.student.pk]),
			{
				"full_name": self.student.full_name,
				"document_number": self.student.document_number,
				"phone": "987654321, 912345678",
				"active": "on",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.student.refresh_from_db()
		self.assertEqual(self.student.phone, "987654321, 912345678")


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
