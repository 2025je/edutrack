from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Campus, User
from payments.forms import PaymentForm, PaymentUpdateForm
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
            receipt_number="D1",
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
                "receipt_number_0": "D",
                "receipt_number_1": "2",
                "enrollment": self.enrollment.pk,
                "amount": "70.00",
                "reference": "Transferencia",
                "notes": "Actualizado",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.receipt_number, "D2")
        self.assertEqual(self.payment.amount, Decimal("70.00"))
        self.assertEqual(
            PaymentAllocation.objects.filter(payment=self.payment).aggregate(total=Sum("amount"))[
                "total"
            ],
            Decimal("70.00"),
        )

    def test_payment_receipt_is_saved_with_uppercase_prefix(self):
        payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="d100",
            amount=10,
        )

        self.assertEqual(payment.receipt_number, "D100")
        payment.refresh_from_db()
        self.assertEqual(payment.receipt_number, "D100")

    def test_receipt_form_uses_optional_letter_and_positive_integer_inputs(self):
        response = self.client.get(reverse("payment-create"))
        self.assertContains(response, 'name="receipt_number_0"')
        self.assertContains(response, 'name="receipt_number_1"')
        self.assertContains(response, "data-uppercase")

        request = RequestFactory().get(reverse("payment-create"))
        request.session = {"selected_campus_id": self.campus.pk}
        request.user = self.user
        cases = [
            ({"receipt_number_0": "", "receipt_number_1": "55"}, "55"),
            ({"receipt_number_0": "d", "receipt_number_1": "100"}, "D100"),
            ({"receipt_number_0": "AB", "receipt_number_1": "5"}, None),
            ({"receipt_number_0": "1", "receipt_number_1": "5"}, None),
            ({"receipt_number_0": "D", "receipt_number_1": "12a"}, None),
            ({"receipt_number_0": "D", "receipt_number_1": "-5"}, None),
            ({"receipt_number_0": "D", "receipt_number_1": "0"}, None),
            ({"receipt_number_0": "D", "receipt_number_1": ""}, None),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                form = PaymentForm(data=data, user=self.user, request=request)
                form.is_valid()
                if expected is None:
                    self.assertIn("receipt_number", form.errors)
                else:
                    self.assertNotIn("receipt_number", form.errors)
                    self.assertEqual(form.cleaned_data["receipt_number"], expected)

    def test_receipt_number_must_be_unique_within_campus_only(self):
        request = RequestFactory().get(reverse("payment-create"))
        request.session = {"selected_campus_id": self.campus.pk}
        request.user = self.user
        same_campus_form = PaymentForm(
            data={"receipt_number_0": "D", "receipt_number_1": "1"},
            user=self.user,
            request=request,
        )
        self.assertFalse(same_campus_form.is_valid())
        self.assertIn("receipt_number", same_campus_form.errors)

        other_campus = Campus.objects.create(name="Otra sede", active=True)
        self.user.campuses.add(other_campus)
        request = RequestFactory().get(reverse("payment-create"))
        request.session = {"selected_campus_id": other_campus.pk}
        request.user = self.user
        other_campus_form = PaymentForm(
            data={"receipt_number_0": "D", "receipt_number_1": "1"},
            user=self.user,
            request=request,
        )
        self.assertFalse(other_campus_form.is_valid())
        self.assertNotIn("receipt_number", other_campus_form.errors)

        other_payment = Payment.objects.create(
            campus=other_campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="D1",
            amount=10,
        )
        self.assertEqual(other_payment.receipt_number, self.payment.receipt_number)

        request = RequestFactory().get(reverse("payment-update", args=[self.payment.pk]))
        request.session = {"selected_campus_id": self.campus.pk}
        request.user = self.user
        update_form = PaymentUpdateForm(
            data={
                "receipt_number_0": "D",
                "receipt_number_1": "1",
                "enrollment": self.enrollment.pk,
                "amount": "40.00",
            },
            instance=self.payment,
            user=self.user,
            request=request,
        )
        self.assertTrue(update_form.is_valid(), update_form.errors)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                campus=self.campus,
                enrollment=self.enrollment,
                cashier=self.user,
                receipt_number="D1",
                amount=10,
            )

    def test_payment_list_filters_and_sorts_receipts_students_and_dates(self):
        other_student = Student.objects.create(
            campus=self.campus,
            full_name="Beatriz de pagos",
        )
        other_course = Course.objects.create(
            campus=self.campus,
            name="Otro curso",
            start_date=date(2026, 10, 14),
        )
        other_enrollment = Enrollment.objects.create(
            campus=self.campus,
            student=other_student,
            course=other_course,
        )
        other_payment = Payment.objects.create(
            campus=self.campus,
            enrollment=other_enrollment,
            cashier=self.user,
            receipt_number="D2",
            amount=20,
        )
        void_payment = Payment.objects.create(
            campus=self.campus,
            enrollment=other_enrollment,
            cashier=self.user,
            receipt_number="D3",
            amount=10,
            status=Payment.Status.VOID,
        )
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.make_aware(datetime(2026, 10, 10, 9, 0))
        )
        Payment.objects.filter(pk=other_payment.pk).update(
            created_at=timezone.make_aware(datetime(2026, 10, 11, 9, 0))
        )
        Payment.objects.filter(pk=void_payment.pk).update(
            created_at=timezone.make_aware(datetime(2026, 10, 12, 9, 0))
        )

        response = self.client.get(reverse("payment-list"), {"sort": "receipt", "direction": "asc"})
        self.assertEqual(response.context["payments"][0].receipt_number, "D1")
        self.assertContains(response, 'name="receipt"')
        self.assertContains(response, 'name="date_from"')
        self.assertContains(response, 'name="date_to"')
        self.assertContains(response, "Fecha de pago - Desde")
        self.assertContains(response, "Fecha de pago - Hasta")
        self.assertNotContains(response, "<th>Sede</th>")
        self.assertContains(response, "?sort=receipt&amp;direction=desc")
        self.assertEqual(response.context["payments"][0].row_number, 1)

        student_sort = self.client.get(
            reverse("payment-list"), {"sort": "student", "direction": "asc"}
        )
        self.assertEqual(student_sort.context["payments"][0].pk, self.payment.pk)
        date_sort = self.client.get(reverse("payment-list"), {"sort": "date", "direction": "asc"})
        self.assertEqual(date_sort.context["payments"][0].pk, self.payment.pk)

        for query, expected_payments in (
            ({"student": "Beatriz"}, [other_payment, void_payment]),
            ({"receipt": "D1"}, self.payment),
            ({"status": "ANULADO"}, void_payment),
            ({"date_from": "2026-10-10", "date_to": "2026-10-10"}, self.payment),
            ({"date_from": "2026-10-13"}, None),
        ):
            with self.subTest(query=query):
                response = self.client.get(reverse("payment-list"), query)
                if expected_payments is None:
                    self.assertEqual(list(response.context["payments"]), [])
                else:
                    if not isinstance(expected_payments, list):
                        expected_payments = [expected_payments]
                    self.assertEqual(
                        {payment.pk for payment in response.context["payments"]},
                        {payment.pk for payment in expected_payments},
                    )

    def test_payment_list_sorts_receipts_by_type_letter_and_number(self):
        for receipt_number in ["44", "1", "7", "D45", "D23", "A43", "A34"]:
            Payment.objects.create(
                campus=self.campus,
                enrollment=self.enrollment,
                cashier=self.user,
                receipt_number=receipt_number,
                amount=1,
            )

        response = self.client.get(reverse("payment-list"), {"sort": "receipt", "direction": "asc"})

        self.assertEqual(
            [payment.receipt_number for payment in response.context["payments"]],
            ["1", "7", "44", "A34", "A43", "D1", "D23", "D45"],
        )

    def test_receipt_check_lists_missing_numeric_receipts(self):
        for receipt_number in ["1", "2", "4", "5"]:
            Payment.objects.create(
                campus=self.campus,
                enrollment=self.enrollment,
                cashier=self.user,
                receipt_number=receipt_number,
                amount=1,
            )

        response = self.client.get(
            reverse("tools"),
            {"receipt_start": "1", "receipt_end": "7", "check_receipts": "1"},
        )

        self.assertEqual(response.context["missing_receipts"], ["3", "6", "7"])
        self.assertContains(response, "3, 6, 7")

    def test_receipt_check_lists_missing_receipts_with_the_same_letter(self):
        for receipt_number in ["D2", "D4", "D5"]:
            Payment.objects.create(
                campus=self.campus,
                enrollment=self.enrollment,
                cashier=self.user,
                receipt_number=receipt_number,
                amount=1,
            )

        response = self.client.get(
            reverse("tools"),
            {"receipt_start": "D1", "receipt_end": "D4", "check_receipts": "1"},
        )

        self.assertEqual(response.context["missing_receipts"], ["D3"])

    def test_receipt_check_rejects_different_letter_prefixes(self):
        response = self.client.get(
            reverse("tools"),
            {"receipt_start": "D1", "receipt_end": "E4", "check_receipts": "1"},
        )

        self.assertIsNone(response.context["missing_receipts"])
        self.assertContains(response, "usar la misma letra")

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
