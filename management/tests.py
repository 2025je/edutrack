import os
import shutil
import tempfile

from core.models import Campus, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from students.models import Course, Promoter, Schedule


class CampusManagementTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="gestor", password="x-clave-123", can_manage_campuses=True
        )
        self.client.force_login(self.manager)
        media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)

    def test_requires_permission(self):
        other = User.objects.create_user(username="sinpermiso", password="x-clave-123")
        self.client.force_login(other)
        for name in ("campus-list", "campus-create"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_sidebar_section_depends_on_permission(self):
        self.assertContains(self.client.get(reverse("campus-list")), reverse("campus-create"))
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

    def test_create_campus_with_optional_flyer(self):
        response = self.client.post(
            reverse("campus-create"),
            {
                "name": "Sede Con Volante",
                "active": "on",
                "flyer-title": "Promo",
                "flyer-file": SimpleUploadedFile("v.pdf", b"%PDF-1.4 x", "application/pdf"),
            },
        )
        self.assertRedirects(response, reverse("campus-list"))
        self.assertEqual(Campus.objects.get(name="Sede Con Volante").flyers.get().title, "Promo")

    def test_create_campus_without_flyer(self):
        self.client.post(reverse("campus-create"), {"name": "Sede Sin Volante", "active": "on"})
        self.assertEqual(Campus.objects.get(name="Sede Sin Volante").flyers.count(), 0)

    def test_create_campus_with_flyer_without_title_uses_file_name(self):
        response = self.client.post(
            reverse("campus-create"),
            {
                "name": "Sede Volante Sin Titulo",
                "active": "on",
                "flyer-file": SimpleUploadedFile("promo.pdf", b"%PDF-1.4 x", "application/pdf"),
            },
        )
        self.assertRedirects(response, reverse("campus-list"))
        campus = Campus.objects.get(name="Sede Volante Sin Titulo")
        self.assertEqual(campus.flyers.get().title, "promo")

    def test_flyer_title_without_file_is_rejected(self):
        response = self.client.post(
            reverse("campus-create"),
            {"name": "Sede Titulo Solo", "active": "on", "flyer-title": "Promo"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Campus.objects.filter(name="Sede Titulo Solo").exists())

    def test_create_page_shows_flyer_section(self):
        response = self.client.get(reverse("campus-create"))
        self.assertContains(response, "flyer-file")
        self.assertFalse(response.context["flyer_form"].use_required_attribute)

    def test_invalid_flyer_blocks_campus_creation(self):
        response = self.client.post(
            reverse("campus-create"),
            {
                "name": "Sede Mala",
                "active": "on",
                "flyer-title": "X",
                "flyer-file": SimpleUploadedFile("v.txt", b"hola", "text/plain"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Campus.objects.filter(name="Sede Mala").exists())

    def test_duplicate_name_is_rejected(self):
        Campus.objects.create(name="Sede Sur")
        response = self.client.post(reverse("campus-create"), {"name": "sede sur", "active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Campus.objects.filter(name__iexact="sede sur").count(), 1)


class CampusFlyerTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="gestor", password="clave-segura-123", can_manage_campuses=True
        )
        self.client.force_login(self.manager)
        self.campus = Campus.objects.create(name="Sede F")
        self.media = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.url = reverse("campus-flyer-create", args=[self.campus.pk])

    def pdf(self, name="volante.pdf", content=b"%PDF-1.4 contenido"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_upload_and_list_flyer(self):
        response = self.client.post(self.url, {"title": "Promo", "file": self.pdf()})
        self.assertRedirects(response, reverse("campus-update", args=[self.campus.pk]))
        flyer = self.campus.flyers.get()
        self.assertEqual(flyer.title, "Promo")
        page = self.client.get(reverse("campus-update", args=[self.campus.pk]))
        self.assertContains(page, "Promo")
        self.assertContains(page, flyer.file.url)

    def test_rejects_invalid_files(self):
        self.client.post(self.url, {"title": "X", "file": self.pdf("a.txt")})
        self.client.post(self.url, {"title": "Y", "file": self.pdf("b.pdf", b"no es pdf")})
        self.client.post(self.url, {"title": "Z", "file": self.pdf("c.png", b"%PDF-1.4 falso")})
        self.assertEqual(self.campus.flyers.count(), 0)

    def test_upload_image_flyer_shows_img_preview(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
        self.client.post(self.url, {"title": "Imagen", "file": self.pdf("v.png", png)})
        self.client.post(
            self.url, {"title": "Foto", "file": self.pdf("v.jpg", b"\xff\xd8\xff\xe0" + b"0" * 20)}
        )
        self.client.post(
            self.url, {"title": "Web", "file": self.pdf("v.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")}
        )
        self.assertEqual(self.campus.flyers.count(), 3)
        self.assertTrue(all(f.is_image for f in self.campus.flyers.all()))
        page = self.client.get(reverse("campus-update", args=[self.campus.pk]))
        self.assertContains(page, 'alt="Vista previa de ', count=3, html=False)

    def test_rejects_oversized_pdf(self):
        big = b"%PDF-" + b"0" * (10 * 1024 * 1024)
        self.client.post(self.url, {"title": "Grande", "file": self.pdf("g.pdf", big)})
        self.assertEqual(self.campus.flyers.count(), 0)

    def test_delete_flyer_removes_file(self):
        self.client.post(self.url, {"title": "Promo", "file": self.pdf()})
        flyer = self.campus.flyers.get()
        path = flyer.file.path
        response = self.client.post(reverse("campus-flyer-delete", args=[flyer.pk]))
        self.assertRedirects(response, reverse("campus-update", args=[self.campus.pk]))
        self.assertEqual(self.campus.flyers.count(), 0)
        self.assertFalse(os.path.exists(path))

    def test_requires_permission_and_post_only(self):
        other = User.objects.create_user(username="sin", password="clave-segura-123")
        self.client.force_login(other)
        response = self.client.post(self.url, {"title": "X", "file": self.pdf()})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.campus.flyers.count(), 0)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 405)


class PromoterCreationTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Promotores", active=True)

    def login(self, **permissions):
        user = User.objects.create_user(username="promo", password="x-test-pass-1", **permissions)
        user.campuses.add(self.campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def test_user_with_permission_creates_promoter_for_selected_campus(self):
        self.login(can_manage_promoters=True)

        response = self.client.post(reverse("promoter-list"), {"name": "  Ana   Pérez "})

        self.assertRedirects(response, reverse("promoter-list"))
        promoter = Promoter.objects.get(name="ANA PÉREZ")
        self.assertEqual(list(promoter.campuses.all()), [self.campus])

    def test_duplicate_promoter_name_is_rejected(self):
        self.login(can_manage_promoters=True)
        Promoter.objects.create(name="Ana Pérez")

        response = self.client.post(reverse("promoter-list"), {"name": "ana pérez"})

        self.assertContains(response, "Ya existe un promotor")
        custom = Promoter.objects.exclude(name__in=["PARTICULAR", "NN"])
        self.assertEqual(custom.count(), 1)
        self.assertEqual(custom.get().name, "ANA PÉREZ")

    def test_user_without_permission_cannot_access_promoters(self):
        self.login(can_manage_students=True, can_register_payments=True)

        self.assertEqual(self.client.get(reverse("promoter-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("promoter-list"), {"name": "X"}).status_code, 403)
        self.assertFalse(Promoter.objects.exclude(name__in=["PARTICULAR", "NN"]).exists())


class CourseCreationTests(TestCase):
    def setUp(self):
        self.campus = Campus.objects.create(name="Sede Cursos", active=True)
        self.schedule = Schedule.objects.create(campus=self.campus, name="Lunes 8:00")

    def login(self, **permissions):
        user = User.objects.create_user(username="cursos", password="x-test-pass-1", **permissions)
        user.campuses.add(self.campus)
        self.client.force_login(user)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()

    def data(self, **overrides):
        data = {
            "name": "Inglés",
            "schedule": self.schedule.pk,
            "group": "1",
            "capacity": "20",
            "start_date": "2026-11-02",
            "enrollment_fee": "40",
            "monthly_fee": "90",
        }
        data.update(overrides)
        return data

    def test_user_with_permission_creates_course_for_selected_campus(self):
        self.login(can_manage_promoters=True)

        response = self.client.post(reverse("course-list"), self.data())

        self.assertRedirects(response, reverse("course-list"))
        course = Course.objects.get(name="INGLÉS")
        self.assertEqual(course.campus, self.campus)
        self.assertEqual(course.schedule, "LUNES 8:00")

    def test_course_form_hides_unassigned_schedule(self):
        self.login(can_manage_promoters=True)

        response = self.client.get(reverse("course-list"))

        self.assertNotIn(
            "PENDIENTE DE ASIGNACION",
            [str(choice[1]) for choice in response.context["form"].fields["schedule"].choices],
        )

    def test_course_form_offers_new_schedule_option(self):
        self.login(can_manage_promoters=True)

        response = self.client.get(reverse("course-list"))

        self.assertContains(response, reverse("schedule-create"))
        self.assertContains(response, "data-uppercase")

    def test_schedules_are_available_only_at_their_campus(self):
        self.login(can_manage_promoters=True)
        other_campus = Campus.objects.create(name="Otra Sede Cursos", active=True)
        other_schedule = Schedule.objects.create(campus=other_campus, name="Lunes 8:00")

        response = self.client.get(reverse("course-list"))

        available_schedule_ids = list(
            response.context["form"].fields["schedule"].queryset.values_list("pk", flat=True)
        )
        self.assertIn(self.schedule.pk, available_schedule_ids)
        self.assertNotIn(other_schedule.pk, available_schedule_ids)
        response = self.client.post(reverse("course-list"), self.data(schedule=other_schedule.pk))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Course.objects.filter(name="INGLÉS").exists())

    def test_catalog_name_inputs_convert_text_to_uppercase(self):
        self.login(can_manage_promoters=True)

        for url_name in ("schedule-create", "promoter-list"):
            with self.subTest(url_name=url_name):
                self.assertContains(self.client.get(reverse(url_name)), "data-uppercase")

    def test_user_with_permission_creates_schedule_used_by_new_courses(self):
        self.login(can_manage_promoters=True)

        response = self.client.post(reverse("schedule-create"), {"name": "  Sábado   9:00 "})

        schedule = Schedule.objects.get(campus=self.campus, name="SÁBADO 9:00")
        self.assertRedirects(
            response,
            f"{reverse('course-list')}?schedule={schedule.pk}",
        )
        page = self.client.get(response.url)
        self.assertContains(page, f'<option value="{schedule.pk}" selected>SÁBADO 9:00</option>')
        self.client.post(reverse("course-list"), self.data(schedule=schedule.pk))
        self.assertEqual(Course.objects.get(name="INGLÉS").schedule, "SÁBADO 9:00")

    def test_duplicate_schedule_is_rejected(self):
        self.login(can_manage_promoters=True)
        before = Schedule.objects.count()

        response = self.client.post(reverse("schedule-create"), {"name": "lunes 8:00"})

        self.assertContains(response, "Ya existe un horario")
        self.assertEqual(Schedule.objects.count(), before)

    def test_same_schedule_name_is_allowed_at_another_campus(self):
        self.login(can_manage_promoters=True)
        other_campus = Campus.objects.create(name="Otra Sede Cursos", active=True)
        user = User.objects.get(username="cursos")
        user.campuses.add(other_campus)
        user = self.client.session
        user["selected_campus_id"] = other_campus.pk
        user.save()

        response = self.client.post(reverse("schedule-create"), {"name": "LUNES 8:00"})

        self.assertRedirects(
            response,
            f"{reverse('course-list')}?schedule="
            f"{Schedule.objects.get(campus=other_campus, name='LUNES 8:00').pk}",
        )

    def test_user_without_permission_cannot_create_schedules(self):
        self.login(can_manage_students=True)

        self.assertEqual(self.client.get(reverse("schedule-create")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("schedule-create"), {"name": "X"}).status_code, 403
        )

    def test_course_start_date_can_be_updated(self):
        self.login(can_manage_promoters=True)
        self.client.post(reverse("course-list"), self.data())
        course = Course.objects.get(name="INGLÉS")
        url = reverse("course-update", args=[course.pk])

        self.assertContains(self.client.get(url), 'type="date"')
        response = self.client.post(
            url,
            {
                "start_date": "2026-12-07",
                "capacity": "30",
                "enrollment_fee": "55",
                "monthly_fee": "120",
                "name": "OTRO",
            },
        )

        self.assertRedirects(response, reverse("course-list"))
        course.refresh_from_db()
        self.assertEqual(course.start_date.isoformat(), "2026-12-07")
        self.assertEqual(
            (course.capacity, int(course.enrollment_fee), int(course.monthly_fee)), (30, 55, 120)
        )
        self.assertEqual(course.name, "INGLÉS")

        invalid = self.client.post(
            url,
            {
                "start_date": "2026-12-07",
                "capacity": "30",
                "enrollment_fee": "0",
                "monthly_fee": "120",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertTrue(invalid.context["form"].errors.get("enrollment_fee"))

    def test_unassigned_course_cannot_be_edited_even_by_superuser(self):
        self.login(can_manage_promoters=True)
        course = Course.objects.get(campus=self.campus, name="POR ASIGNAR")
        url = reverse("course-update", args=[course.pk])

        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"start_date": "2030-01-01"}).status_code, 404)
        self.client.logout()
        root = User.objects.create_superuser("root", password="x")
        self.client.force_login(root)
        session = self.client.session
        session["selected_campus_id"] = self.campus.pk
        session.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unassigned_course_start_date_is_locked_for_non_superusers(self):
        self.login(can_manage_promoters=True)
        course = Course.objects.get(campus=self.campus, name="POR ASIGNAR")

        response = self.client.get(reverse("course-update", args=[course.pk]))

        self.assertEqual(response.status_code, 404)

    def test_duplicate_course_is_rejected(self):
        self.login(can_manage_promoters=True)
        self.client.post(reverse("course-list"), self.data())

        response = self.client.post(reverse("course-list"), self.data(name="inglés"))

        self.assertContains(response, "Ya existe un curso")
        self.assertEqual(Course.objects.exclude(name="POR ASIGNAR").count(), 1)

    def test_user_without_permission_cannot_create_courses(self):
        self.login(can_manage_students=True, can_register_payments=True)

        self.assertEqual(self.client.get(reverse("course-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("course-list"), self.data()).status_code, 403)
        self.assertFalse(Course.objects.exclude(name="POR ASIGNAR").exists())


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
        self.assertEqual(self.client.get(reverse("user-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user-update", args=[other.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("select-campus")), reverse("user-list"))

    def test_sidebar_link_visible_with_permission(self):
        self.assertContains(self.client.get(reverse("user-list")), reverse("user-list"))

    def test_creates_user_with_password_permissions_and_campuses(self):
        response = self.client.post(reverse("user-create"), self.payload())
        self.assertRedirects(response, reverse("user-list"))
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


class UserUpdateTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="gestor", password="clave-segura-123", can_manage_users=True
        )
        self.client.force_login(self.manager)
        self.a = Campus.objects.create(name="A")
        self.b = Campus.objects.create(name="B")
        self.target = User.objects.create_user(
            username="cajero", password="Vieja-clave-123", can_manage_students=True
        )
        self.target.campuses.set([self.a])
        self.url = reverse("user-update", args=[self.target.pk])

    def payload(self, **extra):
        data = {
            "username": "cajero",
            "is_active": "on",
            "campuses": [self.b.pk],
            "can_register_payments": "on",
        }
        data.update(extra)
        return data

    def test_list_shows_users_and_search(self):
        response = self.client.get(reverse("user-list"), {"q": "caj"})
        self.assertContains(response, "cajero")
        self.assertNotContains(self.client.get(reverse("user-list"), {"q": "zzz"}), "cajero")

    def test_edit_updates_username_permissions_and_campuses_keeping_password(self):
        response = self.client.post(self.url, self.payload(username="cajero2"))
        self.assertRedirects(response, reverse("user-list"))
        self.target.refresh_from_db()
        self.assertEqual(self.target.username, "cajero2")
        self.assertTrue(self.target.can_register_payments)
        self.assertFalse(self.target.can_manage_students)
        self.assertEqual(set(self.target.campuses.all()), {self.b})
        self.assertTrue(self.target.check_password("Vieja-clave-123"))

    def test_edit_can_change_password(self):
        self.client.post(
            self.url, self.payload(password1="Nueva-clave-456", password2="Nueva-clave-456")
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("Nueva-clave-456"))

    def test_edit_rejects_mismatched_password(self):
        response = self.client.post(
            self.url, self.payload(password1="Nueva-clave-456", password2="x")
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("Vieja-clave-123"))

    def test_edit_can_deactivate_user_but_not_self(self):
        self.client.post(self.url, {k: v for k, v in self.payload().items() if k != "is_active"})
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        own = reverse("user-update", args=[self.manager.pk])
        response = self.client.post(own, {"username": "gestor", "can_manage_users": "on"})
        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_superusers_and_staff_cannot_be_edited_by_managers(self):
        admin = User.objects.create_superuser(username="root", password="clave-segura-123")
        staff = User.objects.create_user(
            username="staff", password="clave-segura-123", is_staff=True
        )
        for user in (admin, staff):
            self.assertEqual(
                self.client.get(reverse("user-update", args=[user.pk])).status_code, 404
            )
        self.assertNotContains(self.client.get(reverse("user-list")), ">root<")
        self.assertNotContains(self.client.get(reverse("user-list")), "staff")

    def test_edit_cannot_escalate_to_staff_or_superuser(self):
        self.client.post(self.url, self.payload(is_staff="on", is_superuser="on"))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff or self.target.is_superuser)
