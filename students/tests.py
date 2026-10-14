from datetime import date
from io import BytesIO

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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
		self.assertEqual(self.enrollment.record_code, "F-2026-01")

	def test_enrollment_creation_saves_user_selected_date(self):
		new_student = Student.objects.create(
			campus=self.campus,
			full_name="Alumno con fecha elegida",
		)
		response = self.client.get(reverse("enrollment-create"))
		self.assertContains(response, 'type="date"')
		self.assertContains(response, f'value="{timezone.localdate():%Y-%m-%d}"')
		response = self.client.post(
			reverse("enrollment-create"),
			{
				"course": self.course.pk,
				"student": new_student.pk,
				"record_code": "F-2026-FECHA",
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
				"record_code": "F-2026-MULTI",
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

		response = self.client.get(
			reverse("student-enrollment-list", args=[self.student.pk])
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'name="student" value="{self.student.full_name}"')
		self.assertEqual(
			{enrollment.pk for enrollment in response.context["enrollments"]},
			{self.enrollment.pk},
		)
		self.assertNotIn(other_enrollment.pk, {enrollment.pk for enrollment in response.context["enrollments"]})

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
		self.assertContains(response, f'?course_id={self.course.pk}')
		self.assertContains(response, f'?promoter_id={promoter.pk}')
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
		self.assertIn(b"attachment; filename=\"matriculas_", response["Content-Disposition"].encode())
		workbook = load_workbook(BytesIO(response.content), data_only=True)
		worksheet = workbook["Matrículas"]
		rows = list(worksheet.iter_rows(values_only=True))
		self.assertIn("Estudiante de prueba", [value for row in rows for value in row])
		self.assertNotIn("Otro estudiante para exportar", [value for row in rows for value in row])
		self.assertEqual(rows[3][0], "N.º")
		self.assertEqual(rows[4][0], 1)

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
		ranks = {enrollment.pk: enrollment.row_number for enrollment in response.context["enrollments"]}
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
			row[1]: row[0]
			for row in worksheet.iter_rows(min_row=5, values_only=True)
		}
		self.assertEqual(ranks_by_student["Inscripción más antigua"], 1)
		self.assertEqual(ranks_by_student[self.student.full_name], 2)

	def test_enrollment_filters_cover_student_course_record_code_and_promoter(self):
		promoter = Promoter.objects.create(name="Promotor de prueba", active=True)
		self.enrollment.record_code = "FICHA-42"
		self.enrollment.record_code = "FICHA-42"
		self.enrollment.save(update_fields=["record_code"])
		self.enrollment.promoter.add(promoter)

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
				record_code="PAGINADO",
			)

		response = self.client.get(reverse("enrollment-list"), {"record_code": "PAGINADO"})

		self.assertTrue(response.context["is_paginated"])
		self.assertContains(response, "?record_code=PAGINADO&amp;page=2")

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
