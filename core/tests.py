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
