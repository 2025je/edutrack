from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User
from payments.models import Installment, Payment, PaymentAllocation
from calls.models import CallNote, WhatsAppTemplate
from students.models import Course, Enrollment, Student


class CallStudentListTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Llamadas", active=True)
        user = User.objects.create_user(username="caja", password="x", can_manage_calls=True)
        user.campuses.add(self.campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def test_lists_student_phone_courses_and_debt_per_course(self):
        student = Student.objects.create(
            campus=self.campus, full_name="Ana Perez", phone="987654321"
        )
        course = Course.objects.create(
            campus=self.campus, name="Ingles", schedule="Lunes", group="A"
        )
        enrollment = Enrollment.objects.create(campus=self.campus, student=student, course=course)
        installment = Installment.objects.create(
            enrollment=enrollment, concept="Cuota 1", amount=Decimal("100"), due_date=date.today()
        )
        payment = Payment.objects.create(
            campus=self.campus,
            enrollment=enrollment,
            cashier=User.objects.get(username="caja"),
            receipt_number="1",
            amount=Decimal("30"),
        )
        PaymentAllocation.objects.create(
            payment=payment, installment=installment, amount=Decimal("30")
        )

        response = self.client.get(reverse("calls-students"), {"deuda": "1"})

        self.assertEqual(response.status_code, 200)
        row = response.context["rows"][0]
        self.assertEqual(row["student"], student)
        self.assertEqual(row["courses"][0]["debt"], Decimal("70"))
        self.assertContains(response, "https://api.whatsapp.com/send?phone=51987654321&amp;text=")
        self.assertContains(response, "ANA%20PEREZ")
        self.assertEqual([p.receipt_number for p in row["courses"][0]["receipts"]], ["1"])

    def test_template_supports_emojis_and_icon_link(self):
        self.client.post(reverse("calls-template"), {"body": "Hola {alumno} 👋💰"})
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        course = Course.objects.create(campus=self.campus, name="Arte", schedule="L", group="A")
        Enrollment.objects.create(campus=self.campus, student=student, course=course)

        self.assertEqual(
            WhatsAppTemplate.objects.get(campus=self.campus).body, "Hola {alumno} 👋💰"
        )
        response = self.client.get(reverse("calls-students"))

        self.assertContains(response, "text=Hola%20EVA%20%F0%9F%91%8B%F0%9F%92%B0")
        self.assertContains(response, "<svg")

    def test_notes_can_be_added_and_listed_per_student(self):
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        course = Course.objects.create(campus=self.campus, name="Arte", schedule="L", group="A")
        Enrollment.objects.create(campus=self.campus, student=student, course=course)

        response = self.client.post(
            reverse("calls-note-create", args=[student.pk]),
            {"response": "ASISTIRA", "note": "  Pagará el viernes  "},
        )

        self.assertRedirects(response, reverse("calls-notes", args=[student.pk]))
        note = CallNote.objects.get()
        self.assertEqual(
            (note.note, note.student, note.campus), ("Pagará el viernes", student, self.campus)
        )
        self.assertEqual(note.response, CallNote.Response.WILL_ATTEND)
        history = self.client.get(reverse("calls-notes", args=[student.pk]))
        self.assertContains(history, "Pagará el viernes")
        self.assertContains(history, "Asistirá")
        self.assertContains(
            self.client.get(reverse("calls-students")),
            reverse("calls-note-create", args=[student.pk]),
        )
        self.assertEqual(
            self.client.post(
                reverse("calls-note-create", args=[student.pk]), {"response": "OTROS", "note": " "}
            ).status_code,
            200,
        )
        response = self.client.get(reverse("calls-notes-all"), {"q": "viernes"})
        self.assertContains(response, "Pagará el viernes")
        self.assertNotContains(
            self.client.get(reverse("calls-notes-all"), {"q": "zzz"}), "Pagará el viernes"
        )

    def test_note_can_be_edited_and_deleted(self):
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        note = CallNote.objects.create(
            campus=self.campus,
            student=student,
            author=User.objects.get(username="caja"),
            response="OTROS",
            note="Original",
        )
        history = self.client.get(reverse("calls-notes", args=[student.pk]))
        self.assertContains(history, reverse("calls-note-update", args=[note.pk]))
        self.assertContains(history, reverse("calls-note-delete", args=[note.pk]))

        edit_url = reverse("calls-note-update", args=[note.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 200)
        response = self.client.post(
            edit_url,
            {"response": "NO_ASISTIRA", "note": " Cambiado ", "next": reverse("calls-notes-all")},
        )
        self.assertRedirects(response, reverse("calls-notes-all"))
        note.refresh_from_db()
        self.assertEqual((note.response, note.note), ("NO_ASISTIRA", "Cambiado"))

        response = self.client.post(
            edit_url, {"response": "OTROS", "note": "x", "next": "https://evil.example/"}
        )
        self.assertRedirects(response, reverse("calls-notes", args=[student.pk]))

        delete_url = reverse("calls-note-delete", args=[note.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.assertTrue(CallNote.objects.filter(pk=note.pk).exists())
        self.assertRedirects(
            self.client.post(delete_url), reverse("calls-notes", args=[student.pk])
        )
        self.assertFalse(CallNote.objects.filter(pk=note.pk).exists())

    def test_cannot_edit_or_delete_notes_of_other_campus(self):
        other = Campus.objects.create(name="Otra sede", active=True)
        student = Student.objects.create(campus=other, full_name="Ajeno", phone="944444444")
        note = CallNote.objects.create(
            campus=other,
            student=student,
            author=User.objects.get(username="caja"),
            note="Ajena",
        )
        self.assertEqual(
            self.client.get(reverse("calls-note-update", args=[note.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse("calls-note-delete", args=[note.pk])).status_code, 404
        )
        self.assertTrue(CallNote.objects.filter(pk=note.pk).exists())

    def test_invalid_response_type_is_rejected(self):
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        response = self.client.post(
            reverse("calls-note-create", args=[student.pk]), {"response": "XX", "note": "a"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CallNote.objects.exists())

    def test_notes_of_other_campus_students_are_not_accessible(self):
        other = Campus.objects.create(name="Otra sede", active=True)
        foreign = Student.objects.create(campus=other, full_name="Ajeno", phone="944444444")
        self.assertEqual(
            self.client.get(reverse("calls-notes", args=[foreign.pk])).status_code, 404
        )

    def test_users_without_calls_permission_are_denied(self):
        other = User.objects.create_user(
            username="otro", password="x", can_register_payments=True, can_manage_promoters=True
        )
        other.campuses.add(self.campus)
        self.client.force_login(other)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

        for name in ("calls-students", "calls-template", "calls-notes-all"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(self.client.get(reverse("calls-note-update", args=[1])).status_code, 403)
        self.assertEqual(self.client.post(reverse("calls-note-delete", args=[1])).status_code, 403)

    def test_template_can_be_edited_and_is_used_in_message(self):
        response = self.client.post(
            reverse("calls-template"), {"body": "Hola {alumno}, debes S/ {deuda_total}"}
        )
        self.assertRedirects(response, reverse("calls-template"))
        student = Student.objects.create(
            campus=self.campus, full_name="Luis", phone="911111111, 922222222"
        )
        course = Course.objects.create(campus=self.campus, name="Mate", schedule="L", group="A")
        enrollment = Enrollment.objects.create(campus=self.campus, student=student, course=course)
        Installment.objects.create(
            enrollment=enrollment, concept="Cuota", amount=Decimal("20"), due_date=date.today()
        )

        response = self.client.get(reverse("calls-students"))

        self.assertContains(
            response,
            "https://api.whatsapp.com/send?phone=51911111111&amp;text=Hola%20LUIS%2C%20debes%20S%2F%2020.00",
        )
        self.assertContains(response, "https://api.whatsapp.com/send?phone=51922222222&amp;text=")
