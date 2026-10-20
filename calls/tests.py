from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User
from core.testing import create_user, grant, revoke
from payments.models import Installment, Payment, PaymentAllocation
from calls.models import CallAssignment, CallNote, WhatsAppTemplate
from students.models import Course, Enrollment, Student


class CallStudentListTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Llamadas", active=True)
        user = create_user(username="caja", password="x", manage_calls=True, edit_call_notes=True)
        user.campuses.add(self.campus)
        grant(user, "assign_calls")
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
        self.client.post(
            reverse("calls-template"), {"tipo": "BIENVENIDA", "body": "Hola {alumno} 👋💰"}
        )
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        course = Course.objects.create(campus=self.campus, name="Arte", schedule="L", group="A")
        Enrollment.objects.create(campus=self.campus, student=student, course=course)

        self.assertEqual(
            WhatsAppTemplate.objects.get(campus=self.campus, kind="BIENVENIDA").body,
            "Hola {alumno} 👋💰",
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

    def test_editing_notes_requires_its_own_permission(self):
        student = Student.objects.create(campus=self.campus, full_name="Eva", phone="933333333")
        user = User.objects.get(username="caja")
        note = CallNote.objects.create(
            campus=self.campus, student=student, author=user, note="Original"
        )
        revoke(user, "edit_call_notes")
        for name in ("calls-note-update", "calls-note-delete"):
            self.assertEqual(self.client.get(reverse(name, args=[note.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("calls-note-delete", args=[note.pk])).status_code, 403
        )
        self.assertTrue(CallNote.objects.filter(pk=note.pk).exists())
        page = self.client.get(reverse("calls-notes", args=[student.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, reverse("calls-note-update", args=[note.pk]))

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
        other = create_user(
            username="otro", password="x", register_payments=True, manage_promoters=True
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
        self.assertRedirects(response, reverse("calls-template") + "?tipo=DEUDA")
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


class CallAssignmentTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Asignación", active=True)
        self.course = Course.objects.create(
            campus=self.campus, name="Ingles", schedule="L", group="A"
        )
        self.enrollments = []
        for name in ("Ana", "Beto"):
            student = Student.objects.create(campus=self.campus, full_name=name, phone="987654321")
            self.enrollments.append(
                Enrollment.objects.create(campus=self.campus, student=student, course=self.course)
            )
            CallNote.objects.create(
                campus=self.campus, student=student, author=self._user("autor" + name), note="x"
            )
        self.caller = self._user("llamador", manage_calls=True)
        self.boss = self._user("jefe", manage_calls=True, assign_calls=True)

    def _user(self, username, **flags):
        user = create_user(username=username, password="pass-12345", **flags)
        user.campuses.add(self.campus)
        return user

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def test_caller_without_assignments_sees_nothing(self):
        self._login(self.caller)
        self.assertEqual(self.client.get(reverse("calls-students")).context["rows"], [])
        self.assertEqual(len(self.client.get(reverse("calls-notes-all")).context["notes"]), 0)

    def test_caller_sees_only_assigned_enrollments_and_their_history(self):
        CallAssignment.objects.create(user=self.caller, enrollment=self.enrollments[0])
        self._login(self.caller)
        rows = self.client.get(reverse("calls-students")).context["rows"]
        self.assertEqual([r["student"].full_name for r in rows], ["ANA"])
        notes = self.client.get(reverse("calls-notes-all")).context["notes"]
        self.assertEqual([n.student.full_name for n in notes], ["ANA"])
        other = self.enrollments[1].student
        self.assertEqual(self.client.get(reverse("calls-notes", args=[other.pk])).status_code, 404)

    def test_assignment_page_lists_assigned_and_table_without_user(self):
        CallAssignment.objects.create(user=self.caller, enrollment=self.enrollments[0])
        self._login(self.boss)
        url = reverse("calls-assignments")
        page = self.client.get(url)
        self.assertEqual(len(page.context["rows"]), 2)
        self.assertContains(
            page, "Selecciona un usuario arriba para mostrar las casillas de asignación"
        )
        page = self.client.get(url, {"usuario": self.caller.pk, "curso": "Ingles"})
        self.assertContains(page, "Llamadas ya asignadas a llamador (1)")
        self.assertEqual(len(page.context["assigned_list"]), 1)

    def test_assigner_sees_everything(self):
        self._login(self.boss)
        self.assertEqual(len(self.client.get(reverse("calls-students")).context["rows"]), 2)
        self.assertEqual(len(self.client.get(reverse("calls-notes-all")).context["notes"]), 2)

    def test_only_assigner_can_open_assignments(self):
        self._login(self.caller)
        self.assertEqual(self.client.get(reverse("calls-assignments")).status_code, 403)

    def test_assigner_assigns_and_unassigns_shown_enrollments(self):
        self._login(self.boss)
        url = reverse("calls-assignments")
        shown = [e.pk for e in self.enrollments]
        self.client.post(
            url,
            {"usuario": self.caller.pk, "shown": shown, "enrollments": [shown[0]]},
        )
        self.assertEqual(
            list(self.caller.call_assignments.values_list("enrollment_id", flat=True)), [shown[0]]
        )
        self.client.post(url, {"usuario": self.caller.pk, "shown": shown})
        self.assertFalse(self.caller.call_assignments.exists())
        self.assertContains(self.client.get(url, {"usuario": self.caller.pk}), "ANA")

    def test_assignment_filters(self):
        other_course = Course.objects.create(
            campus=self.campus, name="Arte", schedule="M", group="B"
        )
        extra = Enrollment.objects.create(
            campus=self.campus, student=self.enrollments[0].student, course=other_course
        )
        CallAssignment.objects.create(user=self.caller, enrollment=self.enrollments[0])
        self._login(self.boss)
        url = reverse("calls-assignments")

        def ids(**params):
            response = self.client.get(url, {"usuario": self.caller.pk, **params})
            return {r["enrollment"].pk for r in response.context["rows"]}

        self.assertEqual(
            ids(curso="ARTE"),
            {extra.pk} if other_course.name == "ARTE" else ids(curso=other_course.name),
        )
        self.assertEqual(ids(horario="M"), {extra.pk})
        self.assertEqual(ids(grupo="B"), {extra.pk})
        self.assertEqual(ids(estado="asignadas"), {self.enrollments[0].pk})
        self.assertNotIn(self.enrollments[0].pk, ids(estado="sin_asignar"))
        self.assertEqual(ids(estado="otros"), set())


class CallWorkflowTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Flujo", active=True)
        self.course = Course.objects.create(
            campus=self.campus, name="Ingles", schedule="L", group="A"
        )
        self.boss = self._user("jefe", manage_calls=True, assign_calls=True, register_payments=True)
        grant(self.boss, "core.view_call_reports")
        self.ana = self._enroll("Ana", due=date(2000, 1, 1))
        self.beto = self._enroll("Beto", due=date(2999, 1, 1))
        self.caller = self._user("llamador", manage_calls=True)
        self.client.force_login(self.boss)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def _user(self, username, **flags):
        user = create_user(username=username, password="x" * 12, **flags)
        user.campuses.add(self.campus)
        return user

    def _enroll(self, name, due):
        student = Student.objects.create(campus=self.campus, full_name=name, phone="987654321")
        enrollment = Enrollment.objects.create(
            campus=self.campus, student=student, course=self.course
        )
        Installment.objects.create(
            enrollment=enrollment, concept="Cuota", amount=Decimal("50"), due_date=due
        )
        return enrollment

    def rows(self, **params):
        response = self.client.get(reverse("calls-students"), params)
        return [r["student"].full_name for r in response.context["rows"]]

    def quick(self, student, **data):
        return self.client.post(
            reverse("calls-quick-note", args=[student.pk]),
            {"next": reverse("calls-students"), **data},
        )

    def test_quick_note_defaults_detail_to_the_result(self):
        self.quick(self.ana.student, response="NO_CONTESTO", note="")
        note = CallNote.objects.get()
        self.assertEqual(
            (note.note, note.author, note.campus), ("No contestó", self.boss, self.campus)
        )

    def test_promise_requires_a_date(self):
        self.quick(self.ana.student, response="PROMETIO_PAGO")
        self.assertEqual(CallNote.objects.count(), 0)
        self.quick(self.ana.student, response="PROMETIO_PAGO", promise_date="2000-02-01")
        self.assertEqual(CallNote.objects.get().promise_date, date(2000, 2, 1))

    def test_broken_promises_are_flagged_and_filterable(self):
        self.quick(self.ana.student, response="PROMETIO_PAGO", promise_date="2000-02-01")
        self.quick(self.beto.student, response="PROMETIO_PAGO", promise_date="2999-02-01")
        self.assertEqual(self.rows(promesa="vencida"), ["ANA"])
        row = self.client.get(reverse("calls-students")).context["rows"][0]
        self.assertTrue(row["promise_broken"])

    def test_filter_by_last_contact_and_priority_order(self):
        self.quick(self.ana.student, response="NO_CONTESTO")
        self.assertEqual(self.rows(contacto="nunca"), ["BETO"])
        self.assertEqual(self.rows(contacto="7"), ["BETO"])
        self.assertEqual(self.rows(orden="sin_contacto"), ["BETO", "ANA"])
        self.assertEqual(self.rows(orden="vencida"), ["ANA", "BETO"])
        self.assertEqual(self.rows(orden="deuda")[0], "ANA")

    def test_quick_note_requires_permission_to_add_calls(self):
        viewer = self._user("lector")
        grant(viewer, "calls.view_callnote")
        self.client.force_login(viewer)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()
        self.assertEqual(self.quick(self.ana.student, response="OTROS").status_code, 403)

    def test_pay_button_links_to_the_course_with_debt(self):
        page = self.client.get(reverse("calls-students"))
        self.assertContains(page, reverse("payment-create-for", args=[self.ana.pk]))

    def test_bulk_move_passes_every_assignment_to_another_user(self):
        other = self._user("otro", manage_calls=True)
        CallAssignment.objects.create(user=self.caller, enrollment=self.ana)
        CallAssignment.objects.create(user=self.caller, enrollment=self.beto)
        CallAssignment.objects.create(user=other, enrollment=self.beto)
        self.client.post(
            reverse("calls-assignments"),
            {"accion": "reasignar", "origen": self.caller.pk, "usuario": other.pk},
        )
        self.assertFalse(CallAssignment.objects.filter(user=self.caller).exists())
        self.assertEqual(CallAssignment.objects.filter(user=other).count(), 2)

    def test_bulk_split_shares_unassigned_enrollments_evenly(self):
        other = self._user("otro", manage_calls=True)
        extra = self._enroll("Carla", due=date(2999, 1, 1))
        CallAssignment.objects.create(user=self.caller, enrollment=extra)
        self.client.post(
            reverse("calls-assignments"),
            {"accion": "repartir", "reparto": [self.caller.pk, other.pk]},
        )
        self.assertEqual(CallAssignment.objects.filter(user=self.caller).count(), 2)
        self.assertEqual(CallAssignment.objects.filter(user=other).count(), 1)

    def test_report_shows_assignment_progress_per_user(self):
        CallAssignment.objects.create(user=self.caller, enrollment=self.ana)
        CallAssignment.objects.create(user=self.caller, enrollment=self.beto)
        CallNote.objects.create(
            campus=self.campus, student=self.ana.student, author=self.caller, note="x"
        )
        rows = {
            r["author__username"]: r
            for r in self.client.get(reverse("calls-report")).context["rows"]
        }
        row = rows["llamador"]
        self.assertEqual(
            (row["assigned"], row["called"], row["pending"], row["progress"]), (2, 1, 1, 50)
        )
