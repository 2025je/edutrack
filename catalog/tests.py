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
        promoter = Promoter.objects.get(name="Ana Pérez")
        self.assertEqual(list(promoter.campuses.all()), [self.campus])

    def test_duplicate_promoter_name_is_rejected(self):
        self.login(can_manage_promoters=True)
        Promoter.objects.create(name="Ana Pérez")

        response = self.client.post(reverse("promoter-list"), {"name": "ana pérez"})

        self.assertContains(response, "Ya existe un promotor")
        self.assertEqual(Promoter.objects.count(), 1)

    def test_user_without_permission_cannot_access_promoters(self):
        self.login(can_manage_students=True, can_register_payments=True)

        self.assertEqual(self.client.get(reverse("promoter-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("promoter-list"), {"name": "X"}).status_code, 403)
        self.assertFalse(Promoter.objects.exists())


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
        course = Course.objects.get(name="Inglés")
        self.assertEqual(course.campus, self.campus)
        self.assertEqual(course.schedule, "Lunes 8:00")

    def test_course_form_offers_new_schedule_option(self):
        self.login(can_manage_promoters=True)

        response = self.client.get(reverse("course-list"))

        self.assertContains(response, reverse("schedule-create"))

    def test_user_with_permission_creates_schedule_used_by_new_courses(self):
        self.login(can_manage_promoters=True)

        response = self.client.post(reverse("schedule-create"), {"name": "  Sábado   9:00 "})

        self.assertRedirects(
            response,
            f"{reverse('course-list')}?schedule={Schedule.objects.get(name='Sábado 9:00').pk}",
        )
        schedule = Schedule.objects.get(name="Sábado 9:00")
        page = self.client.get(response.url)
        self.assertContains(page, f'<option value="{schedule.pk}" selected>Sábado 9:00</option>')
        self.client.post(reverse("course-list"), self.data(schedule=schedule.pk))
        self.assertEqual(Course.objects.get(name="Inglés").schedule, "Sábado 9:00")

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

    def test_duplicate_course_is_rejected(self):
        self.login(can_manage_promoters=True)
        self.client.post(reverse("course-list"), self.data())

        response = self.client.post(reverse("course-list"), self.data(name="inglés"))

        self.assertContains(response, "Ya existe un curso")
        self.assertEqual(Course.objects.count(), 1)

    def test_user_without_permission_cannot_create_courses(self):
        self.login(can_manage_students=True, can_register_payments=True)

        self.assertEqual(self.client.get(reverse("course-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("course-list"), self.data()).status_code, 403)
        self.assertFalse(Course.objects.exists())
