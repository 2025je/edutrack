from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from calls.models import CallAssignment, CallNote, WhatsAppTemplate
from core.management.commands.seed_test_data import CONFIRMATION, ELEMENTS
from core.models import ActivityLog, Campus, CampusFlyer, User
from payments.models import CashClosing, Installment, Payment, PaymentAllocation
from students.models import Enrollment, Ficha, Student, StudentPhone

PASSWORD = "Demo-Access-2026!"


class SeedTestDataCommandTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.old_campus = Campus.objects.create(name="Sede que será reemplazada")
        User.objects.create_user(username="usuario_anterior", password=PASSWORD)

    def seed(self, inputs=None, *args, menu=False):
        output = StringIO()
        with TemporaryDirectory() as media_root:
            with (
                override_settings(MEDIA_ROOT=media_root),
                mock.patch("sys.stdin.isatty", return_value=True),
                mock.patch(
                    "builtins.input",
                    side_effect=inputs or [CONFIRMATION],
                ),
                mock.patch("getpass.getpass", side_effect=[PASSWORD, PASSWORD]),
            ):
                call_command(
                    "seed_test_data",
                    *(args or (() if menu else ("--all",))),
                    stdout=output,
                    stderr=StringIO(),
                )
                self.media_file_count = sum(path.is_file() for path in Path(media_root).rglob("*"))
        return output.getvalue()

    def test_selection_adds_dependencies_automatically(self):
        output = self.seed(None, "--only=payments")

        self.assertIn("Se añadieron por dependencia", output)
        self.assertEqual(Payment.objects.count(), 3)
        self.assertGreater(Student.objects.count(), 0)
        self.assertGreater(Installment.objects.count(), 0)
        self.assertEqual(CallNote.objects.count(), 0)
        self.assertEqual(CashClosing.objects.count(), 0)
        self.assertEqual(ActivityLog.objects.count(), 0)

    def test_only_campuses_creates_just_admin_and_campuses(self):
        self.seed(None, "--only=campuses")

        self.assertEqual(Campus.objects.count(), 3)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_interactive_menu_by_number(self):
        self.seed([str(list(ELEMENTS).index("students") + 1), CONFIRMATION], menu=True)

        self.assertEqual(Student.objects.count(), 6)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_unknown_element_is_rejected_without_wiping(self):
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            self.assertRaises(CommandError),
        ):
            call_command("seed_test_data", "--only=recibos", stdout=StringIO())
        self.assertTrue(Campus.objects.filter(name="Sede que será reemplazada").exists())

    def test_every_dependency_is_defined_before_use(self):
        keys = list(ELEMENTS)
        for key, (_, requires, _) in ELEMENTS.items():
            for dependency in requires:
                self.assertLess(keys.index(dependency), keys.index(key))

    def test_wipes_old_data_and_creates_all_demo_cases(self):
        old_group_count = Group.objects.count()
        output = self.seed()

        self.assertFalse(Campus.objects.filter(name="Sede que será reemplazada").exists())
        self.assertEqual(Campus.objects.count(), 3)
        self.assertEqual(User.objects.count(), 8)
        self.assertEqual(Student.objects.count(), 6)
        self.assertEqual(StudentPhone.objects.count(), 7)
        self.assertEqual(Enrollment.objects.count(), 6)
        self.assertEqual(Installment.objects.count(), 7)
        self.assertEqual(Payment.objects.count(), 3)
        self.assertEqual(PaymentAllocation.objects.count(), 4)
        self.assertEqual(Ficha.objects.count(), 2)
        self.assertEqual(CashClosing.objects.count(), 1)
        self.assertEqual(CallAssignment.objects.count(), 2)
        self.assertEqual(CallNote.objects.count(), len(CallNote.Response.choices))
        self.assertEqual(WhatsAppTemplate.objects.count(), len(WhatsAppTemplate.Kind.choices))
        self.assertEqual(CampusFlyer.objects.count(), 1)
        self.assertEqual(ActivityLog.objects.count(), 3)
        self.assertEqual(Group.objects.count(), old_group_count)

        current = Enrollment.objects.get(student__full_name="ANA EJEMPLO", active=True)
        self.assertEqual(current.installments.filter(active=True).count(), 5)
        self.assertTrue(current.installments.filter(concept="Mensualidad 2 · parcial").exists())
        self.assertTrue(current.installments.filter(concept="Mensualidad 3 · vencida").exists())
        self.assertTrue(current.installments.filter(concept="Mensualidad 4 · futura").exists())
        self.assertEqual(
            set(Payment.objects.values_list("status", flat=True)),
            {Payment.Status.CONFIRMED, Payment.Status.VOID},
        )
        self.assertTrue(Enrollment.objects.filter(student__isnull=True).exists())
        self.assertTrue(Enrollment.objects.filter(course__isnull=True).exists())
        self.assertEqual(
            Group.objects.get(name="Asignador de llamadas").user_set.get().username,
            "demo_asignador",
        )
        self.assertTrue(User.objects.get(username="demo_admin").is_superuser)
        self.assertTrue(User.objects.get(username="demo_caja").check_password(PASSWORD))
        self.assertGreater(self.media_file_count, 0)
        self.assertIn("demo_gestor", output)

    def test_wrong_confirmation_preserves_existing_data(self):
        output = self.seed(inputs=["no"])

        self.assertIn("Cancelado", output)
        self.assertTrue(Campus.objects.filter(name="Sede que será reemplazada").exists())
        self.assertTrue(User.objects.filter(username="usuario_anterior").exists())
