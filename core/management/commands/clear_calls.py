import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from calls.models import CallClaim, CallNote, WhatsAppSend

CONFIRMATION = "BORRAR LLAMADAS"


class Command(BaseCommand):
    help = (
        "DESTRUCTIVO: borra las llamadas registradas, las reservas de la cola y las marcas de "
        "WhatsApp. Conserva las sublistas, las plantillas y los teléfonos de los alumnos."
    )

    def add_arguments(self, parser):
        parser.add_argument("--campus", type=int, help="Solo borra las llamadas de esta sede (id).")
        parser.add_argument(
            "--yes", action="store_true", help="No pide confirmación (para automatizar)."
        )

    def handle(self, *args, **options):
        querysets = {
            "llamadas": CallNote.objects.all(),
            "reservas de la cola": CallClaim.objects.all(),
            "marcas de WhatsApp": WhatsAppSend.objects.all(),
        }
        if options["campus"]:
            querysets = {
                name: qs.filter(campus_id=options["campus"]) for name, qs in querysets.items()
            }
        counts = {name: qs.count() for name, qs in querysets.items()}
        summary = ", ".join(f"{total} {name}" for name, total in counts.items())

        if not any(counts.values()):
            self.stdout.write("No hay llamadas que borrar.")
            return
        self.stdout.write(self.style.WARNING(f"Se borrarán: {summary}. No se puede deshacer."))
        if not options["yes"]:
            if not sys.stdin.isatty():
                raise CommandError("Use una terminal interactiva (docker exec -it) o --yes.")
            if input(f"Escribe «{CONFIRMATION}» para continuar: ").strip() != CONFIRMATION:
                self.stdout.write("Cancelado. No se modificó nada.")
                return

        with transaction.atomic():
            for qs in querysets.values():
                qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Borrado: {summary}."))
