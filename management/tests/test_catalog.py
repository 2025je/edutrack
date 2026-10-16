from django.test import TestCase
from django.urls import reverse

from core.models import Campus, User
from students.models import Course, Promoter, Schedule


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
        self.schedule = Schedule.objects.create(name="Lunes 8:00")

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

    def test_catalog_name_inputs_convert_text_to_uppercase(self):
        self.login(can_manage_promoters=True)

        for url_name in ("schedule-create", "promoter-list"):
            with self.subTest(url_name=url_name):
                self.assertContains(self.client.get(reverse(url_name)), "data-uppercase")

    def test_user_with_permission_creates_schedule_used_by_new_courses(self):
        self.login(can_manage_promoters=True)

        response = self.client.post(reverse("schedule-create"), {"name": "  Sábado   9:00 "})

        self.assertRedirects(
            response,
            f"{reverse('course-list')}?schedule={Schedule.objects.get(name='SÁBADO 9:00').pk}",
        )
        schedule = Schedule.objects.get(name="SÁBADO 9:00")
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
