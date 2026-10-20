import getpass
import shutil
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

CONFIRMATION = "BORRAR TODO"

# Catálogo que no es dato del usuario: roles con sus permisos (creados por migraciones),
# permisos y tipos de contenido. El resto de tablas se vacía por completo.
KEPT_TABLES = {
    Group._meta.db_table,
    Group.permissions.through._meta.db_table,
    Permission._meta.db_table,
    ContentType._meta.db_table,
}


def tables_to_wipe():
    existing = set(connection.introspection.table_names())
    tables = {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy
    }
    return sorted((tables & existing) - KEPT_TABLES)


def flush_database(tables=None):
    tables = tables if tables is not None else tables_to_wipe()
    statements = connection.ops.sql_flush(
        no_style(), tables, reset_sequences=True, allow_cascade=False
    )
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def wipe_media():
    root = Path(settings.MEDIA_ROOT)
    if not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


class Command(BaseCommand):
    help = (
        "DESTRUCTIVO: elimina todos los usuarios y todos los datos del sistema (como si nunca "
        "hubieran existido), conserva los grupos de roles y crea un superusuario nuevo."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-media",
            action="store_true",
            help="No borra los archivos subidos (fichas, vouchers, volantes, logos).",
        )

    def ask_username(self):
        User = get_user_model()
        while True:
            username = input("Nombre del superusuario: ").strip()
            if not username:
                self.stderr.write("El nombre no puede estar vacío.")
                continue
            try:
                User._meta.get_field("username").run_validators(username)
            except ValidationError as error:
                self.stderr.write(" ".join(error.messages))
                continue
            return username

    def ask_password(self, username):
        User = get_user_model()
        while True:
            password = getpass.getpass("Contraseña: ")
            if password != getpass.getpass("Repite la contraseña: "):
                self.stderr.write("Las contraseñas no coinciden.")
                continue
            try:
                validate_password(password, User(username=username))
            except ValidationError as error:
                for message in error.messages:
                    self.stderr.write(message)
                continue
            return password

    def handle(self, *args, **options):
        if not sys.stdin.isatty():
            raise CommandError("Se necesita una terminal interactiva (use docker exec -it).")
        tables = tables_to_wipe()
        self.stdout.write(
            self.style.WARNING(
                f"Se vaciarán {len(tables)} tablas (usuarios, sedes, estudiantes, matrículas, "
                "pagos, llamadas, registro de actividad, sesiones...)"
                + ("" if options["keep_media"] else " y se borrarán los archivos subidos")
                + ".\nEsta acción NO se puede deshacer. Haz un respaldo antes si lo necesitas."
            )
        )
        if input(f"Escribe «{CONFIRMATION}» para continuar: ").strip() != CONFIRMATION:
            self.stdout.write("Cancelado. No se modificó nada.")
            return

        username = self.ask_username()
        password = self.ask_password(username)

        User = get_user_model()
        with transaction.atomic():
            flush_database(tables)
            User.objects.create_superuser(username=username, email="", password=password)

        cache.clear()
        if not options["keep_media"]:
            wipe_media()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sistema reiniciado. Superusuario «{username}» creado; "
                f"se conservaron {Group.objects.count()} grupos de roles."
            )
        )
