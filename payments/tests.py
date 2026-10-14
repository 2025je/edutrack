from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User
from payments.models import Installment, Payment, PaymentAllocation
from students.models import Course, Enrollment, Student


class PaymentCrudTests(TestCase):
	def setUp(self):
		self.campus = Campus.objects.create(name="Sede de pagos", active=True)
		self.user = User.objects.create_user(
			username="cashier",
			password="secret123",
			can_manage_students=True,
			can_register_payments=True,
		)
		self.user.campuses.add(self.campus)
		self.client.force_login(self.user)
		session = self.client.session
		session["selected_campus_id"] = self.campus.pk
		session.save()
		student = Student.objects.create(campus=self.campus, full_name="Alumno para pago")
		course = Course.objects.create(
			campus=self.campus,
			name="Curso para pago",
			start_date=date(2026, 10, 14),
			enrollment_fee=40,
			monthly_fee=60,
		)
		self.enrollment = Enrollment.objects.create(
			campus=self.campus,
			student=student,
			course=course,
			enrollment_fee=40,
			monthly_fee=60,
		)
		self.installment = Installment.objects.create(
			enrollment=self.enrollment,
			concept="Cuota inicial",
			amount=120,
			due_date=date(2026, 10, 14),
		)
		self.payment = Payment.objects.create(
			campus=self.campus,
			enrollment=self.enrollment,
			cashier=self.user,
			receipt_number="P-001",
			amount=40,
		)
		self.allocation = PaymentAllocation.objects.create(
			payment=self.payment,
			installment=self.installment,
			amount=40,
		)

	def test_payment_can_be_updated_and_reallocated(self):
		response = self.client.get(reverse("payment-update", args=[self.payment.pk]))
		self.assertEqual(response.status_code, 200)
		response = self.client.post(
			reverse("payment-update", args=[self.payment.pk]),
			{
				"receipt_number": "P-002",
				"enrollment": self.enrollment.pk,
				"amount": "70.00",
				"reference": "Transferencia",
				"notes": "Actualizado",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.payment.refresh_from_db()
		self.assertEqual(self.payment.receipt_number, "P-002")
		self.assertEqual(self.payment.amount, Decimal("70.00"))
		self.assertEqual(
			PaymentAllocation.objects.filter(payment=self.payment).aggregate(total=Sum("amount"))["total"],
			Decimal("70.00"),
		)

	def test_payment_can_be_voided_without_deleting_receipt_or_allocation(self):
		response = self.client.get(reverse("payment-delete", args=[self.payment.pk]))
		self.assertEqual(response.status_code, 200)
		response = self.client.post(reverse("payment-delete", args=[self.payment.pk]), follow=True)
		self.assertEqual(response.status_code, 200)
		self.payment.refresh_from_db()
		self.assertEqual(self.payment.status, Payment.Status.VOID)
		self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())
		self.assertTrue(PaymentAllocation.objects.filter(pk=self.allocation.pk).exists())

	def test_payment_form_shows_pending_enrollments_as_single_choice_table(self):
		response = self.client.get(
			reverse("payment-create"),
			{"enrollment": self.enrollment.pk},
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.content.count(b'type="radio"'), 1)
		self.assertContains(response, "Costo matrícula")
		self.assertContains(response, "Mensualidad")
		self.assertContains(response, "Deuda")
		self.assertContains(response, "S/ 40,00")
		self.assertContains(response, "S/ 60,00")
		self.assertContains(response, "S/ 80,00")
		form = response.context["form"]
		self.assertEqual(str(form["enrollment"].value()), str(self.enrollment.pk))
		self.assertEqual(str(form["amount"].value()), "80.00")
