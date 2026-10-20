import os
import subprocess
import sys

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from core.models import ActivityLog, Campus, User
from core.testing import create_user


class CampusLogoTests(TestCase):
    def test_selected_campus_logo_is_shown_in_navigation(self):
        campus = Campus.objects.create(
            name="Sede con logo",
            active=True,
            logo="campus_logos/sede.png",
        )
        user = User.objects.create_superuser(
            username="campus-admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = campus.pk
        session.save()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="/media/campus_logos/sede.png"')
        self.assertContains(response, 'alt="Logo de Sede con logo"')

    def test_navigation_omits_logo_when_campus_has_none(self):
        campus = Campus.objects.create(name="Sede sin logo", active=True)
        user = User.objects.create_superuser(
            username="campus-admin-no-logo",
            email="admin-no-logo@example.com",
            password="test-password-123",
        )
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = campus.pk
        session.save()

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'src="/media/campus_logos/')

    def test_header_combobox_lists_campuses_and_switches_back_to_current_page(self):
        first = Campus.objects.create(name="Sede A", active=True)
        second = Campus.objects.create(name="Sede B", active=True)
        user = User.objects.create_superuser(
            username="switcher",
            email="switcher@example.com",
            password="pass12345",
        )
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = first.pk
        session.save()

        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, f'<button type="submit" name="campus" value="{second.pk}">')
        self.assertContains(page, "<strong>Sede A</strong>")

        response = self.client.post(
            reverse("select-campus"), {"campus": second.pk, "next": reverse("course-list")}
        )
        self.assertRedirects(response, reverse("course-list"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["selected_campus_id"], second.pk)

    def test_switch_ignores_external_next_url(self):
        campus = Campus.objects.create(name="Sede C", active=True)
        user = User.objects.create_superuser(
            username="switcher2",
            email="switcher2@example.com",
            password="pass12345",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("select-campus"), {"campus": campus.pk, "next": "https://evil.example/"}
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)


class ActivityLogTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede A", active=True)
        self.admin = User.objects.create_superuser(
            username="ADMIN", email="a@x.com", password="x-Pass-12345"
        )
        self.worker = create_user(
            username="CAJERO", password="x-Pass-12345", register_payments=True
        )
        self.worker.campuses.add(self.campus)

    def test_login_logout_and_failed_login_are_recorded(self):
        self.client.post(reverse("login"), {"username": "CAJERO", "password": "mala"})
        self.client.post(reverse("login"), {"username": "CAJERO", "password": "x-Pass-12345"})
        self.client.post(reverse("logout"))
        actions = list(ActivityLog.objects.order_by("id").values_list("action", "username"))
        self.assertEqual(
            actions,
            [("login_failed", "CAJERO"), ("login", "CAJERO"), ("logout", "CAJERO")],
        )

    def test_successful_write_is_recorded_but_reads_and_errors_are_not(self):
        self.client.force_login(self.worker)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()
        self.client.get(reverse("payment-list"))
        self.assertEqual(ActivityLog.objects.count(), 0)
        self.client.post(reverse("select-campus"), {"campus": self.campus.pk})
        log = ActivityLog.objects.get()
        self.assertEqual((log.username, log.campus), ("CAJERO", self.campus))
        self.assertEqual(log.method, "POST")

    def test_only_superusers_can_see_activity_view(self):
        ActivityLog.objects.create(username="CAJERO", action="login", description="Inició sesión")
        self.client.force_login(self.worker)
        self.assertEqual(self.client.get(reverse("activity-log")).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("activity-log"), {"user": "CAJERO", "action": "login"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inició sesión")
        response = self.client.get(reverse("activity-log"), {"action": "delete"})
        self.assertNotContains(response, "Inició sesión")


class RoleGroupMatrixTests(TestCase):
    """Los grupos iniciales (migración 0013) concretan la matriz de permisos."""

    def user_in(self, *group_names):
        from django.contrib.auth.models import Group

        user = User.objects.create_user(username="u" + str(User.objects.count()), password="x")
        user.groups.set(Group.objects.filter(name__in=group_names))
        campus = Campus.objects.get_or_create(name="Sede")[0]
        user.campuses.add(campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = campus.pk
        session.save()
        return user

    def test_six_groups_exist(self):
        from django.contrib.auth.models import Group

        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)),
            {
                "Matrículas",
                "Caja",
                "Gestor de llamadas",
                "Asignador de llamadas",
                "Supervisor de campus",
                "Administrador general",
            },
        )

    def test_special_permissions_are_not_granted_by_default(self):
        user = self.user_in("Matrículas", "Caja", "Supervisor de campus", "Administrador general")
        for perm in (
            "core.deactivate_student",
            "core.deactivate_enrollment",
            "core.change_enrollment_course",
            "core.void_payment",
            "core.edit_call_notes",
            "core.assign_calls",
            "core.export_reports",
        ):
            self.assertEqual(user.has_perm(perm), perm == "core.export_reports", perm)

    def test_permissions_accumulate_across_groups(self):
        user = self.user_in("Matrículas", "Caja")
        self.assertTrue(user.has_perm("students.add_enrollment"))
        self.assertTrue(user.has_perm("payments.add_payment"))
        self.assertFalse(user.has_perm("calls.add_callnote"))

    def test_views_enforce_group_permissions(self):
        self.user_in("Caja")
        self.assertEqual(self.client.get(reverse("payment-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("student-create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("enrollment-excel")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user-list")).status_code, 403)

    def test_pending_balances_are_separate_from_payments(self):
        from core.testing import grant

        self.user_in("Caja")
        self.assertEqual(self.client.get(reverse("payment-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("installment-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pending-debts")).status_code, 200)
        user = self.user_in()
        grant(user, "payments.view_payment")
        self.assertEqual(self.client.get(reverse("payment-list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("installment-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pending-debts")).status_code, 403)

    def test_call_report_requires_permission(self):
        self.user_in("Gestor de llamadas")
        self.assertEqual(self.client.get(reverse("calls-report")).status_code, 403)
        self.user_in("Administrador general")
        response = self.client.get(reverse("calls-report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reporte de llamadas")

    def test_call_report_scope_and_totals(self):
        from calls.models import CallNote
        from core.testing import grant
        from students.models import Student

        user = self.user_in()
        grant(user, "core.view_call_reports")
        campus = user.campuses.first()
        other = User.objects.create_user(username="otro", password="x-Pass-12345")
        student = Student.objects.create(campus=campus, full_name="Ana")
        for author in (user, user, other):
            CallNote.objects.create(
                campus=campus,
                student=student,
                author=author,
                response=CallNote.Response.WILL_ATTEND,
                note="x",
            )
        response = self.client.get(reverse("calls-report"))
        self.assertEqual(response.context["totals"]["total"], 2)
        grant(user, "core.view_all_calls")
        response = self.client.get(reverse("calls-report"))
        self.assertEqual(response.context["totals"]["total"], 3)

    def test_profile_shows_account_and_changes_password(self):
        user = create_user(username="perfil", password="x-Pass-12345")
        self.client.force_login(user)
        page = self.client.get(reverse("profile"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "perfil")
        response = self.client.post(
            reverse("profile"),
            {
                "old_password": "x-Pass-12345",
                "new_password1": "Nueva-clave-98765",
                "new_password2": "Nueva-clave-98765",
            },
        )
        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("Nueva-clave-98765"))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)

    def test_profile_describes_permissions_in_spanish(self):
        self.user_in("Caja")
        page = self.client.get(reverse("profile"))
        self.assertContains(page, "Registrar pagos")
        self.assertContains(page, "Ver cuotas y saldos pendientes")
        self.assertNotContains(page, "Can add")

    def test_every_permission_has_spanish_description(self):
        from django.contrib.auth.models import Permission

        from core.permission_labels import describe

        for perm in Permission.objects.filter(
            content_type__app_label__in=["core", "students", "payments", "calls", "auth"]
        ).select_related("content_type"):
            if perm.content_type.model in {"logentry", "contenttype", "session"}:
                continue
            _, name, detail = describe(perm)
            self.assertNotRegex(name, r"^Can |^Puede ", perm.codename)
            self.assertTrue(detail, perm.codename)

    def test_sidebar_only_shows_what_the_user_can_use(self):
        self.user_in("Caja")
        page = self.client.get(reverse("dashboard"))
        for shown in (
            reverse("payment-list"),
            reverse("installment-list"),
            reverse("global-search"),
        ):
            self.assertContains(page, f'href="{shown}"')
        for hidden in (
            reverse("student-create"),
            reverse("enrollment-list"),
            reverse("calls-students"),
            reverse("calls-report"),
            reverse("user-list"),
            reverse("campus-list"),
            reverse("promoter-list"),
        ):
            self.assertNotContains(page, f'href="{hidden}"')

    def test_sidebar_can_collapse_and_navigates_partially(self):
        self.user_in("Caja")
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, 'id="sidebar-toggle"')
        self.assertContains(page, "js/sidebar.js")
        from django.contrib.staticfiles import finders

        with open(finders.find("js/sidebar.js"), encoding="utf-8") as script:
            self.assertIn("Navegación parcial", script.read())

    def test_search_finds_sections_without_searching_records(self):
        from students.models import Student

        self.user_in("Caja")
        Student.objects.create(campus=Campus.objects.get(name="Sede"), full_name="Ana Prueba")
        page = self.client.get(reverse("global-search"), {"q": "ana"})
        self.assertNotContains(page, "ANA PRUEBA")
        page = self.client.get(reverse("global-search"), {"q": "recibos"})
        self.assertContains(page, f'href="{reverse("payment-list")}"')

    def test_search_only_lists_sections_the_user_can_open(self):
        self.user_in("Gestor de llamadas")
        self.assertEqual(self.client.get(reverse("global-search")).status_code, 200)
        page = self.client.get(reverse("global-search"), {"q": "usuarios"})
        self.assertNotContains(page, f'href="{reverse("user-list")}"')
        page = self.client.get(reverse("global-search"), {"q": "segui"})
        self.assertContains(page, f'href="{reverse("calls-students")}"')

    def test_search_finds_subsections_and_quick_filters_and_returns_json(self):
        self.user_in("Administrador general")
        response = self.client.get(reverse("global-search"), {"q": "llamar hoy", "json": "1"})
        urls = [r["url"] for r in response.json()["results"]]
        self.assertIn(reverse("calls-students") + "?promesa=hoy", urls)
        self.user_in("Gestor de llamadas")
        response = self.client.get(reverse("global-search"), {"q": "plantilla promesa"})
        self.assertContains(response, "?tipo=PROMESA")

    def test_search_matches_without_accents_and_limits_json_results(self):
        self.user_in("Administrador general")
        response = self.client.get(reverse("global-search"), {"q": "matricula", "json": "1"})
        names = [r["name"] for r in response.json()["results"]]
        self.assertIn("Matrículas", names)
        self.assertLessEqual(len(names), 12)
        self.assertEqual(
            self.client.get(reverse("global-search"), {"q": "", "json": "1"}).json(),
            {"results": []},
        )

    def test_enrollment_staff_cannot_void_payments_or_manage_users(self):
        self.user_in("Matrículas")
        self.assertEqual(self.client.get(reverse("student-create")).status_code, 200)
        self.assertEqual(self.client.get(reverse("payment-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user-create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("campus-list")).status_code, 403)

    def test_call_manager_sees_calls_but_not_assignments(self):
        self.user_in("Gestor de llamadas")
        self.assertEqual(self.client.get(reverse("calls-students")).status_code, 200)
        self.assertEqual(self.client.get(reverse("calls-assignments")).status_code, 403)
        self.user_in("Asignador de llamadas")
        self.assertEqual(self.client.get(reverse("calls-assignments")).status_code, 200)

    def test_administrator_manages_users_and_campuses_without_superuser(self):
        user = self.user_in("Administrador general")
        self.assertFalse(user.is_superuser)
        for name in ("user-list", "user-create", "campus-list", "campus-create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class SecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="cajera", password="clave-correcta-123")

    def login(self, password):
        return self.client.post(
            reverse("login"), {"username": "cajera", "password": password}, REMOTE_ADDR="10.0.0.5"
        )

    def test_login_is_locked_after_repeated_failures(self):
        for _ in range(5):
            self.assertNotContains(self.login("mala"), "Demasiados intentos")
        locked = self.login("clave-correcta-123")
        self.assertContains(locked, "Demasiados intentos")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_resets_the_counter(self):
        for _ in range(3):
            self.login("mala")
        self.assertEqual(self.login("clave-correcta-123").status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.login("mala")
        self.assertEqual(self.login("clave-correcta-123").status_code, 302)

    def test_lockout_does_not_affect_other_users(self):
        User.objects.create_user(username="otro", password="clave-correcta-123")
        for _ in range(6):
            self.login("mala")
        response = self.client.post(
            reverse("login"),
            {"username": "otro", "password": "clave-correcta-123"},
            REMOTE_ADDR="10.0.0.5",
        )
        self.assertEqual(response.status_code, 302)

    def test_health_endpoint_is_public(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_media_requires_login_and_hides_unknown_files(self):
        self.assertEqual(self.client.get("/media/vouchers/x.png").status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/media/vouchers/x.png").status_code, 404)
        self.assertEqual(self.client.get("/media/campus_logos/x.png").status_code, 200)

    def test_production_refuses_to_start_without_a_secret_key(self):
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SECRET_KEY"}
        env.update(DJANGO_DEBUG="False", DJANGO_SETTINGS_MODULE="config.settings")
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)


class DashboardCacheTests(TestCase):
    def test_version_changes_when_data_changes(self):
        from core.dashboard_cache import current_version
        from students.models import Student

        campus = Campus.objects.create(name="Sede cache", active=True)
        before = current_version()
        Student.objects.create(campus=campus, full_name="Alumno cache")
        self.assertGreater(current_version(), before)


class RecordHistoryTests(TestCase):
    def setUp(self):
        from payments.models import Payment
        from students.models import Course, Enrollment, Student

        self.campus = Campus.objects.create(name="Sede Historial", active=True)
        self.user = create_user(
            username="hist", password="x" * 12, manage_students=True, register_payments=True
        )
        self.user.campuses.add(self.campus)
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()
        self.student = Student.objects.create(campus=self.campus, full_name="Ana Historia")
        course = Course.objects.create(campus=self.campus, name="Curso H")
        self.enrollment = Enrollment.objects.create(
            campus=self.campus, student=self.student, course=course
        )
        self.payment = Payment.objects.create(
            campus=self.campus,
            enrollment=self.enrollment,
            cashier=self.user,
            receipt_number="H1",
            amount=10,
        )

    def test_actions_are_linked_to_their_student_and_enrollment(self):
        self.client.get(reverse("payment-receipt", args=[self.payment.pk]))
        log = ActivityLog.objects.filter(description__startswith="Consultó un recibo").first()
        self.assertEqual((log.object_type, log.object_id), ("enrollment", self.enrollment.pk))
        page = self.client.get(reverse("record-history", args=["matricula", self.enrollment.pk]))
        self.assertContains(page, "Consultó un recibo")

    def test_history_is_scoped_to_the_selected_campus_and_permissions(self):
        ActivityLog.objects.create(
            username="x",
            action="update",
            description="Cambio visible",
            object_type="student",
            object_id=self.student.pk,
        )
        url = reverse("record-history", args=["estudiante", self.student.pk])
        self.assertContains(self.client.get(url), "Cambio visible")
        other = Campus.objects.create(name="Otra sede", active=True)
        self.user.campuses.add(other)
        session = self.client.session
        session["selected_campus_id"] = other.pk
        session.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("record-history", args=["otro", 1])).status_code, 404
        )


class AvailableCampusesTests(TestCase):
    def test_superuser_sees_inactive_campuses_but_regular_user_does_not(self):
        from core.campus import available_campuses

        active = Campus.objects.create(name="Sede activa", active=True)
        inactive = Campus.objects.create(name="Sede inactiva", active=False)
        admin = User.objects.create_superuser(username="root", password="x" * 12)
        user = create_user(username="regular", password="x" * 12)
        user.campuses.add(active, inactive)

        self.assertCountEqual(available_campuses(admin), [active, inactive])
        self.assertCountEqual(available_campuses(user), [active])
