from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User


class CampusManagementTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="gestor", password="x-clave-123", can_manage_campuses=True
        )
        self.client.force_login(self.manager)

    def test_requires_permission(self):
        other = User.objects.create_user(username="sinpermiso", password="x-clave-123")
        self.client.force_login(other)
        for name in ("campus-list", "campus-create", "campus-users"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_sidebar_section_depends_on_permission(self):
        self.assertContains(self.client.get(reverse("campus-list")), reverse("campus-users"))
        other = User.objects.create_user(username="sinpermiso", password="x-clave-123")
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse("select-campus")), reverse("campus-list"))

    def test_create_and_edit_campus(self):
        response = self.client.post(
            reverse("campus-create"), {"name": "Sede Norte", "address": "Av. 1", "active": "on"}
        )
        self.assertRedirects(response, reverse("campus-list"))
        campus = Campus.objects.get(name="Sede Norte")
        self.client.post(
            reverse("campus-update", args=[campus.pk]), {"name": "Sede Norte 2", "address": ""}
        )
        campus.refresh_from_db()
        self.assertEqual(campus.name, "Sede Norte 2")
        self.assertFalse(campus.active)

    def test_duplicate_name_is_rejected(self):
        Campus.objects.create(name="Sede Sur")
        response = self.client.post(reverse("campus-create"), {"name": "sede sur", "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Campus.objects.filter(name__iexact="sede sur").count(), 1)

    def test_assign_campuses_to_user(self):
        a = Campus.objects.create(name="A")
        b = Campus.objects.create(name="B")
        target = User.objects.create_user(username="cajero", password="x-clave-123")
        self.assertContains(self.client.get(reverse("campus-users")), "cajero")
        response = self.client.post(
            reverse("campus-user-update", args=[target.pk]), {"campuses": [a.pk, b.pk]}
        )
        self.assertRedirects(response, reverse("campus-users"))
        self.assertEqual(set(target.campuses.all()), {a, b})
        self.client.post(reverse("campus-user-update", args=[target.pk]), {"campuses": [b.pk]})
        self.assertEqual(set(target.campuses.all()), {b})

    def test_superusers_cannot_be_managed_here(self):
        admin = User.objects.create_superuser(username="superadmin-x", password="x-clave-123")
        self.assertEqual(
            self.client.get(reverse("campus-user-update", args=[admin.pk])).status_code, 404
        )
        self.assertNotContains(self.client.get(reverse("campus-users")), "superadmin-x")
