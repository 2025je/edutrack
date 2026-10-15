from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User


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
        self.assertContains(page, "<span>Sede: Sede A</span>")

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
