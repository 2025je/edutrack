from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User


class UserCreateTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="gestor", password="clave-segura-123", can_manage_users=True
        )
        self.client.force_login(self.manager)
        self.campus = Campus.objects.create(name="Sede A")

    def payload(self, **extra):
        data = {
            "username": "nuevo",
            "password1": "Clave-muy-Segura-987",
            "password2": "Clave-muy-Segura-987",
            "campuses": [self.campus.pk],
            "can_register_payments": "on",
        }
        data.update(extra)
        return data

    def test_requires_permission(self):
        other = User.objects.create_user(username="sinpermiso", password="clave-segura-123")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("user-create")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("select-campus")), reverse("user-create"))

    def test_sidebar_link_visible_with_permission(self):
        self.assertContains(self.client.get(reverse("user-create")), reverse("user-create"))

    def test_creates_user_with_password_permissions_and_campuses(self):
        response = self.client.post(reverse("user-create"), self.payload())
        self.assertRedirects(response, reverse("user-create"))
        user = User.objects.get(username="nuevo")
        self.assertTrue(user.check_password("Clave-muy-Segura-987"))
        self.assertTrue(user.can_register_payments)
        self.assertFalse(user.can_manage_students)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(set(user.campuses.all()), {self.campus})

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(reverse("user-create"), self.payload(password2="otra"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("user-create"), self.payload(password1="123", password2="123")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nuevo").exists())

    def test_cannot_escalate_to_staff_or_superuser(self):
        self.client.post(reverse("user-create"), self.payload(is_staff="on", is_superuser="on"))
        user = User.objects.get(username="nuevo")
        self.assertFalse(user.is_staff or user.is_superuser)
