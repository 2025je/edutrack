import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Campus, User
from core.testing import create_user, grant, revoke
from payments.models import Installment, Payment, PaymentAllocation
from calls.call_queue import expire_stale
from calls.consumers import CallQueueConsumer
from calls.realtime import broadcast
from calls.models import (
    CallClaim,
    CallList,
    CallListMember,
    CallNote,
    WhatsAppSend,
    WhatsAppTemplate,
)
from students.models import Course, Enrollment, Student, StudentPhone


def make_list(campus, name, enrollments=(), users=()):
    call_list = CallList.objects.create(campus=campus, name=name)
    call_list.enrollments.set(enrollments)
    for user in users:
        CallListMember.objects.create(call_list=call_list, user=user)
    return call_list


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

    def test_caller_cannot_open_follow_up_and_sees_nothing_without_assignments(self):
        self._login(self.caller)
        self.assertEqual(self.client.get(reverse("calls-students")).status_code, 403)
        self.assertEqual(len(self.client.get(reverse("calls-notes-all")).context["notes"]), 0)

    def test_caller_sees_only_assigned_enrollments_and_their_history(self):
        make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.caller)
        self.assertEqual(self.client.get(reverse("calls-students")).status_code, 403)
        notes = self.client.get(reverse("calls-notes-all")).context["notes"]
        self.assertEqual([n.student.full_name for n in notes], ["ANA"])
        other = self.enrollments[1].student
        self.assertEqual(self.client.get(reverse("calls-notes", args=[other.pk])).status_code, 404)

    def test_assignment_page_previews_filtered_enrollments_and_existing_lists(self):
        make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.boss)
        url = reverse("calls-assignments")
        page = self.client.get(url)
        self.assertEqual(len(page.context["rows"]), 2)
        self.assertContains(page, "Sublistas existentes")
        self.assertContains(page, "Lista A")
        self.assertContains(page, "Ver las 1 matrícula")
        self.assertContains(page, "<details")
        self.assertNotContains(page, 'name="enrollments" value')
        page = self.client.get(url, {"q": "ANA"})
        self.assertEqual(len(page.context["rows"]), 1)
        self.assertEqual(page.context["all_ids"], str(self.enrollments[0].pk))

    def test_enrollments_outside_the_campus_are_not_added_to_a_list(self):
        other_campus = Campus.objects.create(name="Otra sede", active=True)
        foreign_course = Course.objects.create(
            campus=other_campus, name="X", schedule="M", group="A"
        )
        foreign = Enrollment.objects.create(
            campus=other_campus, student=self.enrollments[0].student, course=foreign_course
        )
        self._login(self.boss)
        self.client.post(
            reverse("calls-assignments"),
            {
                "accion": "crear_lista",
                "nombre": "Mixta",
                "enrollments": [self.enrollments[0].pk, foreign.pk],
            },
        )
        self.assertEqual(
            list(CallList.objects.get().enrollments.values_list("pk", flat=True)),
            [self.enrollments[0].pk],
        )

    def test_assigner_sees_everything(self):
        self._login(self.boss)
        self.assertEqual(len(self.client.get(reverse("calls-students")).context["rows"]), 2)
        self.assertEqual(len(self.client.get(reverse("calls-notes-all")).context["notes"]), 2)

    def test_only_assigner_can_open_assignments(self):
        self._login(self.caller)
        self.assertEqual(self.client.get(reverse("calls-assignments")).status_code, 403)

    def test_assigner_creates_a_list_with_the_filtered_enrollments(self):
        self._login(self.boss)
        url = reverse("calls-assignments")
        self.client.post(
            url,
            {
                "accion": "crear_lista",
                "nombre": "  Morosos   inglés ",
                "enrollments": [self.enrollments[0].pk],
            },
        )
        call_list = CallList.objects.get()
        self.assertEqual((call_list.name, call_list.created_by), ("Morosos inglés", self.boss))
        self.assertEqual([e.student.full_name for e in call_list.enrollments.all()], ["ANA"])
        self.client.post(url, {"accion": "crear_lista", "nombre": "morosos INGLÉS"})
        self.assertEqual(CallList.objects.count(), 1)

    def test_one_list_can_have_many_users_who_share_its_enrollments(self):
        second = self._user("llamador2", manage_calls=True)
        self._login(self.boss)
        self.client.post(
            reverse("calls-assignments"),
            {
                "accion": "crear_lista",
                "nombre": "Lista A",
                "usuarios": [self.caller.pk, second.pk],
                "enrollments": [self.enrollments[0].pk],
            },
        )
        call_list = CallList.objects.get()
        self.assertEqual(call_list.members.count(), 2)
        for user in (self.caller, second):
            self._login(user)
            notes = self.client.get(reverse("calls-notes-all")).context["notes"]
            self.assertEqual([n.student.full_name for n in notes], ["ANA"])

    def test_user_already_in_another_list_cannot_be_assigned(self):
        first = make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.boss)
        url = reverse("calls-assignments")
        response = self.client.post(
            url,
            {"accion": "crear_lista", "nombre": "Lista B", "usuarios": [self.caller.pk]},
            follow=True,
        )
        self.assertContains(response, "ya pertenece a otra sublista")
        self.assertFalse(CallList.objects.filter(name="Lista B").exists())
        self.assertEqual(self.caller.call_membership.call_list, first)
        self.assertContains(self.client.get(url), "bloqueado: ya está en «Lista A»")

    def test_user_can_move_after_being_removed_from_the_previous_list(self):
        first = make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.boss)
        url = reverse("calls-assignments")
        member = first.members.get()
        self.client.post(url, {"accion": "quitar_usuario", "lista": first.pk, "miembro": member.pk})
        self.assertFalse(first.members.exists())
        self.client.post(
            url, {"accion": "crear_lista", "nombre": "Lista B", "usuarios": [self.caller.pk]}
        )
        self.assertEqual(CallListMember.objects.get(user=self.caller).call_list.name, "Lista B")

    def test_enrollment_can_be_removed_from_a_list_without_deleting_it(self):
        call_list = make_list(self.campus, "Lista A", self.enrollments)
        self._login(self.boss)
        self.client.post(
            reverse("calls-assignments"),
            {
                "accion": "quitar_matricula",
                "lista": call_list.pk,
                "matricula": self.enrollments[0].pk,
            },
        )
        self.assertEqual(
            list(call_list.enrollments.values_list("pk", flat=True)), [self.enrollments[1].pk]
        )
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_list_names_are_unique_per_campus_ignoring_case(self):
        make_list(self.campus, "Lista A", [])
        with self.assertRaises(IntegrityError), transaction.atomic():
            CallList.objects.create(campus=self.campus, name="LISTA a")
        self._login(self.boss)
        response = self.client.post(
            reverse("calls-assignments"),
            {"accion": "crear_lista", "nombre": " lista   a "},
            follow=True,
        )
        self.assertContains(response, "Ya existe una sublista llamada")
        self.assertEqual(CallList.objects.count(), 1)

    def test_database_rejects_a_user_in_two_lists(self):
        make_list(self.campus, "Lista A", [], [self.caller])
        other = CallList.objects.create(campus=self.campus, name="Lista B")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CallListMember.objects.create(call_list=other, user=self.caller)

    def test_deleting_a_list_frees_its_users(self):
        call_list = make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.boss)
        self.client.post(
            reverse("calls-assignments"), {"accion": "eliminar_lista", "lista": call_list.pk}
        )
        self.assertFalse(CallList.objects.exists())
        self.assertFalse(CallListMember.objects.exists())
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_lists_of_other_campuses_are_not_reachable(self):
        other_campus = Campus.objects.create(name="Otra sede", active=True)
        foreign = make_list(other_campus, "Ajena", [], [self.caller])
        self._login(self.boss)
        url = reverse("calls-assignments")
        self.client.post(
            url,
            {
                "accion": "quitar_usuario",
                "lista": foreign.pk,
                "miembro": foreign.members.get().pk,
            },
        )
        self.client.post(url, {"accion": "eliminar_lista", "lista": foreign.pk})
        self.assertTrue(foreign.members.exists())
        self.assertTrue(CallList.objects.filter(pk=foreign.pk).exists())

    def test_creating_a_list_with_users_state_and_filter_in_one_form(self):
        second = self._user("llamador2", manage_calls=True)
        self._login(self.boss)
        url = reverse("calls-assignments")
        self.client.post(
            url,
            {
                "accion": "crear_lista",
                "nombre": "Todo junto",
                "estado_lista": "inactiva",
                "usuarios": [self.caller.pk, second.pk],
                "enrollments": [self.enrollments[0].pk],
            },
        )
        call_list = CallList.objects.get(name="Todo junto")
        self.assertFalse(call_list.active)
        self.assertEqual(call_list.members.count(), 2)
        self.assertEqual([e.student.full_name for e in call_list.enrollments.all()], ["ANA"])
        self._login(self.caller)
        self.assertEqual(len(self.client.get(reverse("calls-notes-all")).context["notes"]), 0)
        call_list.active = True
        call_list.save()
        notes = self.client.get(reverse("calls-notes-all")).context["notes"]
        self.assertEqual([n.student.full_name for n in notes], ["ANA"])

    def test_create_with_a_busy_user_is_rejected_without_creating_the_list(self):
        make_list(self.campus, "Lista A", [], [self.caller])
        self._login(self.boss)
        self.client.post(
            reverse("calls-assignments"),
            {"accion": "crear_lista", "nombre": "Nueva", "usuarios": [self.caller.pk]},
        )
        self.assertFalse(CallList.objects.filter(name="Nueva").exists())

    def test_assignment_form_lists_callers_without_selecting_a_list(self):
        outsider = self._user("sinsede", manage_calls=True)
        outsider.campuses.clear()
        self._login(self.boss)
        response = self.client.get(reverse("calls-assignments"))
        self.assertContains(response, "sinsede")
        self.assertContains(response, "no tiene acceso a esta sede")
        self.client.post(
            reverse("calls-assignments"),
            {"accion": "crear_lista", "nombre": "X", "usuarios": [outsider.pk]},
        )
        self.assertFalse(CallListMember.objects.filter(user=outsider).exists())
        self.assertContains(response, 'name="usuarios"')
        self.assertContains(response, 'name="estado_lista"')

    def test_assignment_filters(self):
        other_course = Course.objects.create(
            campus=self.campus, name="Arte", schedule="M", group="B"
        )
        extra = Enrollment.objects.create(
            campus=self.campus, student=self.enrollments[0].student, course=other_course
        )
        target = make_list(self.campus, "Lista A", [self.enrollments[0]], [self.caller])
        self._login(self.boss)
        url = reverse("calls-assignments")

        def ids(**params):
            response = self.client.get(url, {"lista": target.pk, **params})
            return {r["enrollment"].pk for r in response.context["rows"]}

        self.assertEqual(
            ids(curso="ARTE"),
            {extra.pk} if other_course.name == "ARTE" else ids(curso=other_course.name),
        )
        self.assertEqual(ids(horario="M"), {extra.pk})
        self.assertEqual(ids(grupo="B"), {extra.pk})
        self.assertEqual(ids(estado="en_alguna"), {self.enrollments[0].pk})
        self.assertNotIn(self.enrollments[0].pk, ids(estado="sin_asignar"))
        Enrollment.objects.filter(pk=extra.pk).update(enrollment_date="2026-01-10")
        Course.objects.exclude(pk=other_course.pk).update(start_date="2026-02-01")
        Course.objects.filter(pk=other_course.pk).update(start_date="2026-03-01")
        self.assertEqual(
            ids(matricula_desde="2026-01-10", matricula_hasta="2026-01-10"), {extra.pk}
        )
        self.assertEqual(ids(inicio_desde="2026-03-01", inicio_hasta="2026-03-31"), {extra.pk})
        self.assertEqual(ids(inicio_desde="2026-04-01"), set())
        today = timezone.localdate()
        Course.objects.filter(pk=other_course.pk).update(start_date=today + timedelta(days=10))
        Enrollment.objects.filter(pk=extra.pk).update(enrollment_date=today)
        self.assertEqual(ids(situacion="por_iniciar"), {extra.pk})
        self.assertNotIn(extra.pk, ids(situacion="ya_inicio"))
        Enrollment.objects.filter(pk=extra.pk).update(enrollment_date=today + timedelta(days=11))
        self.assertIn(extra.pk, ids(situacion="incorporacion"))
        Course.objects.filter(pk=other_course.pk).update(start_date=today - timedelta(days=20))
        Enrollment.objects.filter(pk=extra.pk).update(enrollment_date=today - timedelta(days=30))
        self.assertIn(extra.pk, ids(situacion="ya_inicio"))
        self.assertNotIn(extra.pk, ids(situacion="incorporacion"))
        self.assertFalse(Enrollment.objects.get(pk=extra.pk).is_incorporation)
        Enrollment.objects.filter(pk=extra.pk).update(enrollment_date=today)
        self.assertTrue(Enrollment.objects.get(pk=extra.pk).is_incorporation)
        self.assertContains(
            self.client.get(url, {"situacion": "incorporacion"}),
            "chip orange darken-2",
        )


class CallQueueTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Cola", active=True)
        course = Course.objects.create(campus=self.campus, name="Ingles", schedule="L", group="A")
        self.enrollments = []
        for name in ("Ana", "Beto", "Carla"):
            student = Student.objects.create(campus=self.campus, full_name=name, phone="987654321")
            self.enrollments.append(
                Enrollment.objects.create(campus=self.campus, student=student, course=course)
            )
        self.u1 = self._user("uno")
        self.u2 = self._user("dos")
        self.outsider = self._user("fuera")
        self.call_list = make_list(self.campus, "Cola", self.enrollments, [self.u1, self.u2])

    def _user(self, username):
        user = create_user(username=username, password="x" * 12, manage_calls=True)
        user.campuses.add(self.campus)
        return user

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def _ask(self, user):
        self._login(user)
        return self.client.post(reverse("calls-queue"), {"accion": "pedir"})

    def test_user_without_list_cannot_ask(self):
        self._ask(self.outsider)
        self.assertEqual(CallClaim.objects.count(), 0)

    def test_two_users_get_different_students(self):
        self._ask(self.u1)
        self._ask(self.u2)
        students = set(CallClaim.objects.values_list("student_id", flat=True))
        self.assertEqual(len(students), 2)

    def test_claim_card_lists_every_course_with_debt_and_total(self):
        student = self.enrollments[0].student
        other = Course.objects.create(campus=self.campus, name="Redes", schedule="M", group="B")
        second = Enrollment.objects.create(campus=self.campus, student=student, course=other)
        for enrollment, amount in ((self.enrollments[0], "100"), (second, "50")):
            Installment.objects.create(
                enrollment=enrollment,
                concept="Cuota",
                amount=Decimal(amount),
                due_date=date.today(),
            )
        CallClaim.objects.create(
            campus=self.campus, user=self.u1, call_list=self.call_list, student=student
        )
        self._login(self.u1)
        page = self.client.get(reverse("calls-queue"))
        self.assertContains(page, "INGLES")
        self.assertContains(page, "REDES")
        self.assertContains(page, "Deuda total: S/ 150,00")

    def test_asking_twice_keeps_same_claim(self):
        self._ask(self.u1)
        self._ask(self.u1)
        self.assertEqual(CallClaim.objects.filter(user=self.u1).count(), 1)

    def test_teammate_sees_claim_in_status(self):
        self._ask(self.u1)
        self._login(self.u2)
        data = self.client.get(reverse("calls-queue-status")).json()
        self.assertEqual([c["user"] for c in data["team"]], ["uno"])

    def test_claim_expires(self):
        self._ask(self.u1)
        CallClaim.objects.update(started_at=timezone.now() - timedelta(minutes=30))
        self._login(self.u2)
        self.assertEqual(self.client.get(reverse("calls-queue-status")).json()["team"], [])
        self.assertEqual(CallClaim.objects.get().status, CallClaim.Status.EXPIRED)

    def test_release_returns_student_to_queue(self):
        self._ask(self.u1)
        self.client.post(reverse("calls-queue"), {"accion": "liberar"})
        self.assertEqual(CallClaim.objects.get().status, CallClaim.Status.RELEASED)

    def test_saving_note_finishes_claim(self):
        self._ask(self.u1)
        claim = CallClaim.objects.get()
        response = self.client.post(
            reverse("calls-quick-note", args=[claim.student_id]),
            {"response": "NO_CONTESTO", "note": "", "next": reverse("calls-queue")},
        )
        self.assertEqual(response.status_code, 302)
        claim.refresh_from_db()
        self.assertEqual(claim.status, CallClaim.Status.DONE)

    def test_contacted_students_are_not_offered_again(self):
        for _ in range(3):
            self._ask(self.u1)
            claim = CallClaim.objects.get(user=self.u1, status=CallClaim.Status.ACTIVE)
            self.client.post(
                reverse("calls-quick-note", args=[claim.student_id]),
                {"response": "ASISTIRA", "note": ""},
            )
        self._ask(self.u1)
        self.assertFalse(CallClaim.objects.filter(status=CallClaim.Status.ACTIVE).exists())

    def test_no_answer_students_can_be_requested_again(self):
        for _ in range(3):
            self._ask(self.u1)
            claim = CallClaim.objects.get(user=self.u1, status=CallClaim.Status.ACTIVE)
            self.client.post(
                reverse("calls-quick-note", args=[claim.student_id]),
                {"response": "NO_CONTESTO", "note": ""},
            )
        self._ask(self.u1)
        self.assertTrue(CallClaim.objects.filter(status=CallClaim.Status.ACTIVE).exists())

    def test_summary_table_shows_called_calling_and_not_called(self):
        self._ask(self.u1)
        first = CallClaim.objects.get().student
        self.client.post(
            reverse("calls-quick-note", args=[first.pk]),
            {"response": "ASISTIRA", "note": ""},
        )
        self._ask(self.u2)
        second = CallClaim.objects.get(status=CallClaim.Status.ACTIVE).student
        rows = {
            r["student"].pk: r for r in self.client.get(reverse("calls-queue")).context["history"]
        }
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[first.pk]["state"], "Llamado")
        self.assertTrue(rows[first.pk]["answered"])
        self.assertEqual(rows[second.pk]["state"], "Llamando")
        self.assertEqual(rows[second.pk]["caller"], "dos")
        others = [r for pk, r in rows.items() if pk not in (first.pk, second.pk)]
        self.assertEqual(others[0]["state"], "Sin llamar")
        self.assertIsNone(others[0]["answered"])

    def test_summary_leaves_result_empty_when_not_answered(self):
        self._ask(self.u1)
        student = CallClaim.objects.get().student
        self.client.post(
            reverse("calls-quick-note", args=[student.pk]),
            {"response": "NO_CONTESTO", "note": ""},
        )
        rows = {
            r["student"].pk: r for r in self.client.get(reverse("calls-queue")).context["history"]
        }
        self.assertFalse(rows[student.pk]["answered"])
        rows = self.client.get(reverse("calls-queue-status")).json()["history_rows"]
        row = next(r for r in rows if r["id"] == student.pk)
        self.assertIs(row["answered"], False)
        self.assertEqual(row["response"], "NO_CONTESTO")

    def test_wrong_number_is_saved_and_shown_as_not_answered(self):
        self._ask(self.u1)
        student = CallClaim.objects.get().student
        self.client.post(
            reverse("calls-quick-note", args=[student.pk]),
            {"response": "TELEFONO_EQUIVOCADO", "note": ""},
        )
        note = CallNote.objects.get()
        self.assertEqual(note.get_response_display(), "Teléfono equivocado")
        rows = {
            r["student"].pk: r for r in self.client.get(reverse("calls-queue")).context["history"]
        }
        self.assertFalse(rows[student.pk]["answered"])
        rows = self.client.get(reverse("calls-queue-status")).json()["history_rows"]
        row = next(r for r in rows if r["id"] == student.pk)
        self.assertEqual(row["label"], "Teléfono equivocado")
        self.assertFalse(row["retry"])

    def test_wrong_number_disables_only_the_selected_phone(self):
        self._ask(self.u1)
        student = CallClaim.objects.get().student
        student.phone = "987654321, 912345678"
        student.save()
        StudentPhone.objects.create(student=student, number="987654321")
        StudentPhone.objects.create(student=student, number="912345678")
        url = reverse("calls-quick-note", args=[student.pk])
        self.client.post(url, {"response": "TELEFONO_EQUIVOCADO", "note": ""})
        self.assertFalse(CallNote.objects.exists())
        self.client.post(
            url, {"response": "TELEFONO_EQUIVOCADO", "note": "", "wrong_phone": "912345678"}
        )
        student.refresh_from_db()
        self.assertEqual(student.phone, "987654321")
        self.assertEqual(student.phones.count(), 2)
        self.assertTrue(student.phones.get(number="912345678").invalid)
        self.assertFalse(student.phones.get(number="987654321").invalid)
        self.assertEqual(CallNote.objects.get().note, "Teléfono equivocado: 912345678")

    def test_student_without_valid_phone_is_not_offered(self):
        for student in Student.objects.filter(campus=self.campus):
            student.phone = ""
            student.save()
        self._ask(self.u1)
        self.assertFalse(CallClaim.objects.exists())

    def test_wrong_number_with_a_single_phone_disables_it_without_choosing(self):
        self._ask(self.u1)
        student = CallClaim.objects.get().student
        self.client.post(
            reverse("calls-quick-note", args=[student.pk]),
            {"response": "TELEFONO_EQUIVOCADO", "note": ""},
        )
        student.refresh_from_db()
        self.assertEqual(student.phone, "")
        self.assertTrue(student.phones.get().invalid)

    def test_wrong_number_with_another_valid_phone_can_be_requested_again(self):
        self._ask(self.u1)
        student = CallClaim.objects.get().student
        student.phone = "987654321, 912345678"
        student.save()
        StudentPhone.objects.create(student=student, number="987654321")
        StudentPhone.objects.create(student=student, number="912345678")
        self.client.post(
            reverse("calls-quick-note", args=[student.pk]),
            {"response": "TELEFONO_EQUIVOCADO", "note": "", "wrong_phone": "912345678"},
        )
        rows = self.client.get(reverse("calls-queue-status")).json()["history_rows"]
        self.assertTrue(next(r for r in rows if r["id"] == student.pk)["retry"])
        self.client.post(reverse("calls-queue"), {"accion": "pedir", "alumno": student.pk})
        self.assertTrue(
            CallClaim.objects.filter(student=student, status=CallClaim.Status.ACTIVE).exists()
        )

    def test_can_call_again_a_specific_student_who_did_not_answer(self):
        self._ask(self.u1)
        student_id = CallClaim.objects.get().student_id
        self.client.post(
            reverse("calls-quick-note", args=[student_id]),
            {"response": "NO_CONTESTO", "note": ""},
        )
        page = self.client.get(reverse("calls-queue"))
        self.assertContains(page, "Volver a llamar")
        self.client.post(reverse("calls-queue"), {"accion": "pedir", "alumno": student_id})
        self.assertTrue(
            CallClaim.objects.filter(
                user=self.u1, student_id=student_id, status=CallClaim.Status.ACTIVE
            ).exists()
        )

    def test_status_includes_updated_history_table(self):
        self._ask(self.u1)
        student_id = CallClaim.objects.get().student_id
        self.client.post(
            reverse("calls-quick-note", args=[student_id]),
            {"response": "NO_CONTESTO", "note": ""},
        )
        self._login(self.u2)
        rows = self.client.get(reverse("calls-queue-status")).json()["history_rows"]
        row = next(r for r in rows if r["id"] == student_id)
        self.assertIs(row["answered"], False)
        self.assertTrue(row["retry"])
        self.assertEqual(row["url"], reverse("calls-notes", args=[student_id]))

    def test_clear_calls_command_deletes_activity_but_keeps_lists(self):
        from django.core.management import call_command

        student = self.enrollments[0].student
        CallNote.objects.create(campus=self.campus, student=student, author=self.u1, note="x")
        CallClaim.objects.create(
            campus=self.campus, user=self.u1, call_list=self.call_list, student=student
        )
        WhatsAppSend.objects.create(campus=self.campus, student=student, user=self.u1)
        call_command("clear_calls", "--yes", stdout=StringIO())
        self.assertEqual(CallNote.objects.count(), 0)
        self.assertEqual(CallClaim.objects.count(), 0)
        self.assertEqual(WhatsAppSend.objects.count(), 0)
        self.assertEqual(CallList.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 3)

    def test_whatsapp_checkbox_is_saved_and_shown_to_the_team(self):
        self._ask(self.u1)
        student_id = CallClaim.objects.get().student_id
        url = reverse("calls-whatsapp-mark", args=[student_id])
        self.assertEqual(self.client.post(url, {"enviado": "1"}).status_code, 200)
        self.client.post(url, {"enviado": "1"})
        self.assertEqual(WhatsAppSend.objects.filter(student_id=student_id).count(), 1)
        self._login(self.u2)
        rows = self.client.get(reverse("calls-queue-status")).json()["history_rows"]
        row = next(r for r in rows if r["id"] == student_id)
        self.assertTrue(row["whatsapp"])
        self.assertTrue(row["can_send"])
        self.assertEqual(row["open_url"], reverse("calls-whatsapp-open", args=[student_id]))
        self.assertFalse(next(r for r in rows if r["id"] != student_id)["whatsapp"])
        self.client.post(url, {"enviado": "0"})
        self.assertFalse(WhatsAppSend.objects.exists())

    def test_whatsapp_send_button_redirects_without_marking_as_sent(self):
        self._ask(self.u1)
        student_id = CallClaim.objects.get().student_id
        response = self.client.get(reverse("calls-whatsapp-open", args=[student_id]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://api.whatsapp.com/send?phone=51"))
        self.assertFalse(WhatsAppSend.objects.exists())

    def test_whatsapp_endpoints_require_call_permission(self):
        user = create_user(username="sinperm2", password="x" * 12)
        user.campuses.add(self.campus)
        self._login(user)
        student = Student.objects.filter(campus=self.campus).first()
        self.assertEqual(
            self.client.post(
                reverse("calls-whatsapp-mark", args=[student.pk]), {"enviado": "1"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("calls-whatsapp-open", args=[student.pk])).status_code, 403
        )

    def test_requires_permission(self):
        user = create_user(username="sinperm", password="x" * 12)
        user.campuses.add(self.campus)
        self._login(user)
        self.assertEqual(self.client.get(reverse("calls-queue")).status_code, 403)


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

    def test_report_shows_assignment_progress_per_user(self):
        make_list(self.campus, "Lista", [self.ana, self.beto], [self.caller])
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


IN_MEMORY_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


class RealtimeFixture:
    path = "/ws/llamadas/cola/"

    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Vivo", active=True)
        self.other_campus = Campus.objects.create(name="Otra Sede", active=True)
        course = Course.objects.create(campus=self.campus, name="Ingles", schedule="L", group="A")
        student = Student.objects.create(campus=self.campus, full_name="Ana", phone="987654321")
        enrollment = Enrollment.objects.create(campus=self.campus, student=student, course=course)
        self.user = create_user(username="vivo", password="x" * 12, manage_calls=True)
        self.user.campuses.add(self.campus)
        self.call_list = make_list(self.campus, "Cola", [enrollment], [self.user])


# El consumer abre sus propias consultas (database_sync_to_async), que cierran la conexión
# de un TestCase; por eso estas pruebas usan TransactionTestCase.
@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS)
class CallQueueConsumerTests(RealtimeFixture, TransactionTestCase):
    serialized_rollback = True

    async def _connect(self, user, campus_id):
        communicator = ApplicationCommunicator(
            CallQueueConsumer.as_asgi(),
            {
                "type": "websocket",
                "path": self.path,
                "headers": [],
                "subprotocols": [],
                "user": user,
                "session": {"selected_campus_id": campus_id},
            },
        )
        await communicator.send_input({"type": "websocket.connect"})
        reply = await communicator.receive_output(timeout=3)
        return communicator, reply["type"] == "websocket.accept"

    async def _disconnect(self, communicator):
        await communicator.send_input({"type": "websocket.disconnect", "code": 1000})
        await communicator.wait(timeout=3)

    async def test_member_receives_changes_of_their_campus(self):
        communicator, connected = await self._connect(self.user, self.campus.pk)
        self.assertTrue(connected)
        await sync_to_async(broadcast)(self.other_campus.pk)
        self.assertTrue(await communicator.receive_nothing(timeout=0.3))
        await sync_to_async(broadcast)(self.campus.pk)
        message = await communicator.receive_output(timeout=3)
        self.assertEqual(json.loads(message["text"]), {"type": "changed"})
        await self._disconnect(communicator)

    async def test_rejects_anonymous_unauthorized_or_foreign_campus(self):
        outsider = await sync_to_async(create_user)(username="nada", password="x" * 12)
        await sync_to_async(outsider.campuses.add)(self.campus)
        for user, campus_id in (
            (AnonymousUser(), self.campus.pk),
            (outsider, self.campus.pk),
            (self.user, self.other_campus.pk),
            (self.user, None),
        ):
            communicator, connected = await self._connect(user, campus_id)
            self.assertFalse(connected)
            await self._disconnect(communicator)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_LAYERS)
class CallQueueNotifyTests(RealtimeFixture, TestCase):
    def _login(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def test_queue_actions_notify_the_campus(self):
        self._login()
        with patch("calls.realtime.broadcast") as sent:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("calls-queue"), {"accion": "pedir"})
            sent.assert_called_with(self.campus.pk)
            sent.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("calls-queue"), {"accion": "liberar"})
            sent.assert_called_with(self.campus.pk)

    def test_note_and_whatsapp_mark_notify_the_campus(self):
        self._login()
        student = Student.objects.get()
        with patch("calls.realtime.broadcast") as sent:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse("calls-whatsapp-mark", args=[student.pk]), {"enviado": "1"}
                )
            sent.assert_called_with(self.campus.pk)
            sent.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                CallNote.objects.create(
                    campus=self.campus, student=student, author=self.user, note="hola"
                )
            sent.assert_called_with(self.campus.pk)

    def test_expired_claims_notify_the_campus(self):
        CallClaim.objects.create(
            campus=self.campus,
            call_list=self.call_list,
            student=Student.objects.get(),
            user=self.user,
        )
        CallClaim.objects.update(
            started_at=timezone.now() - timedelta(minutes=CallClaim.MINUTES + 1)
        )
        with patch("calls.realtime.broadcast") as sent:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(expire_stale(self.call_list), 1)
            sent.assert_called_once_with(self.campus.pk)

    def test_failed_broadcast_does_not_break_the_request(self):
        self._login()
        with (
            patch("calls.realtime.get_channel_layer", side_effect=OSError("redis caido")),
            self.assertLogs("calls.realtime", "WARNING"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("calls-queue"), {"accion": "pedir"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CallClaim.objects.filter(status=CallClaim.Status.ACTIVE).exists())
