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

    def test_search_requires_permission_and_hides_unusable_actions(self):
        self.user_in("Gestor de llamadas")
        self.assertEqual(self.client.get(reverse("global-search")).status_code, 403)
        page = self.client.get(reverse("dashboard"))
        self.assertNotContains(page, f'href="{reverse("global-search")}"')
        self.assertNotContains(page, 'name="q"')

    def test_search_results_only_offer_permitted_actions(self):
        from students.models import Student

        self.user_in("Supervisor de campus")
        Student.objects.create(campus=Campus.objects.get(name="Sede"), full_name="Ana Prueba")
        page = self.client.get(reverse("global-search"), {"q": "Ana"})
        self.assertContains(page, "ANA PRUEBA")
        self.assertContains(page, "Matrículas")
        self.assertNotContains(page, "/editar/")

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
