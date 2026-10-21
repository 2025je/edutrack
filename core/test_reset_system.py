from io import StringIO
from unittest import mock, skipUnless

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

from core.management.commands.reset_system import CONFIRMATION
from core.models import ActivityLog, Campus, User
from students.models import Student

PASSWORD = "Contrasena-Segura-2026"


class ResetSystemTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.campus = Campus.objects.create(name="Sede", active=True)
        self.old = User.objects.create_superuser("viejo", "", "x" * 12)
        self.old.campuses.add(self.campus)
        Student.objects.create(campus=self.campus, full_name="ANA", phone="911111111")
        ActivityLog.objects.create(username="viejo", action="login", description="Inició sesión")
        self.groups = Group.objects.count()

    def run_command(self, inputs, passwords):
        out = StringIO()
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=inputs),
            mock.patch("getpass.getpass", side_effect=passwords),
        ):
            call_command("reset_system", "--keep-media", stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_wipes_everything_and_creates_only_the_new_superuser(self):
        self.run_command([CONFIRMATION, "nuevo"], [PASSWORD, PASSWORD])

        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["nuevo"])
        user = User.objects.get()
        self.assertTrue(user.is_superuser and user.is_staff)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.pk, 1)
        self.assertEqual(Campus.objects.count(), 0)
        self.assertEqual(Student.objects.count(), 0)
        self.assertEqual(ActivityLog.objects.count(), 0)
        self.assertEqual(Group.objects.count(), self.groups)
        self.assertGreater(self.groups, 0)

    def test_works_with_terminal_colors_enabled(self):
        out = StringIO()
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=[CONFIRMATION, "nuevo"]),
            mock.patch("getpass.getpass", side_effect=[PASSWORD, PASSWORD]),
        ):
            call_command("reset_system", "--keep-media", "--force-color", stdout=out)

        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["nuevo"])

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL TRUNCATE CASCADE regression")
    def test_wipes_legacy_referencing_tables_and_preserves_catalogs(self):
        preserved_models = (Group, Permission, ContentType, MigrationRecorder.Migration)
        preserved_rows = {
            model: list(model.objects.order_by("pk").values()) for model in preserved_models
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE calls_callmessage ("
                "id integer PRIMARY KEY, campus_id bigint REFERENCES core_campus (id))"
            )
            self.addCleanup(self.drop_legacy_table)
            cursor.execute(
                "INSERT INTO calls_callmessage (id, campus_id) VALUES (%s, %s)",
                [1, self.campus.pk],
            )

        self.run_command([CONFIRMATION, "nuevo"], [PASSWORD, PASSWORD])

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM calls_callmessage")
            self.assertEqual(cursor.fetchone()[0], 0)
        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["nuevo"])
        for model, rows in preserved_rows.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(list(model.objects.order_by("pk").values()), rows)

    def drop_legacy_table(self):
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE calls_callmessage")

    def test_wrong_confirmation_changes_nothing(self):
        output = self.run_command(["no"], [])

        self.assertIn("Cancelado", output)
        self.assertTrue(User.objects.filter(username="viejo").exists())
        self.assertEqual(Student.objects.count(), 1)

    def test_requires_interactive_terminal(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(CommandError):
                call_command("reset_system", "--keep-media", stdout=StringIO())
        self.assertEqual(Student.objects.count(), 1)
