import getpass
import sys
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from calls.models import CallAssignment, CallNote, WhatsAppTemplate
from core.management.commands.reset_system import flush_database, tables_to_wipe, wipe_media
from core.models import ActivityLog, Campus, CampusFlyer
from payments.models import CashClosing, Installment, Payment, PaymentAllocation
from students.models import (
    Course,
    Enrollment,
    Ficha,
    Promoter,
    Schedule,
    Student,
    StudentPhone,
)

CONFIRMATION = "BORRAR Y CREAR DATOS"
ADMIN_USERNAME = "demo_admin"
ROLE_USERS = {
    "demo_matriculas": "Matrículas",
    "demo_caja": "Caja",
    "demo_gestor": "Gestor de llamadas",
    "demo_asignador": "Asignador de llamadas",
    "demo_supervisor": "Supervisor de campus",
    "demo_administrador": "Administrador general",
    "demo_catalogo": "Gestor de catálogo académico",
}
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0000004010100c9fe92ef0000000049454e44ae426082"
)
DEMO_PDF = b"%PDF-1.4\n% Archivo ficticio de demostracion EduTrack\n%%EOF\n"


def seed_campuses(ctx):
    ctx.central = Campus.objects.create(
        name="Sede Central Demo", address="Av. Ejemplo 123", active=True
    )
    ctx.north = Campus.objects.create(
        name="Sede Norte Demo", address="Calle Ficticia 456", active=True
    )
    ctx.inactive_campus = Campus.objects.create(
        name="Sede Inactiva Demo", address="Dirección de prueba", active=False
    )


def seed_flyers(ctx):
    ctx.central.logo.save("logo-demo.png", ContentFile(PNG_1X1), save=True)
    flyer = CampusFlyer(campus=ctx.central, title="Volante ficticio de bienvenida")
    flyer.file.save("volante-demo.pdf", ContentFile(DEMO_PDF), save=True)


def seed_users(ctx):
    User = get_user_model()
    ctx.users = {}
    for username, role in ROLE_USERS.items():
        user = User.objects.create_user(username=username, password=ctx.password)
        user.groups.add(Group.objects.get(name=role))
        user.campuses.add(ctx.central)
        ctx.users[username] = user
    ctx.users["demo_gestor"].campuses.add(ctx.north)
    ctx.admin.campuses.add(ctx.central, ctx.north, ctx.inactive_campus)


def seed_schedules(ctx):
    Schedule.objects.bulk_create(
        [
            Schedule(campus=ctx.central, name="MAÑANA"),
            Schedule(campus=ctx.central, name="TARDE"),
            Schedule(campus=ctx.north, name="NOCHE"),
        ]
    )


def seed_promoters(ctx):
    ctx.promoter_main = Promoter.objects.create(name="Promotor Demo Central")
    ctx.promoter_main.campuses.add(ctx.central)
    promoter_north = Promoter.objects.create(name="Promotor Demo Norte")
    promoter_north.campuses.add(ctx.north)


def seed_courses(ctx):
    today = ctx.today
    ctx.english = Course.objects.create(
        campus=ctx.central,
        name="Inglés Demo",
        schedule="Lunes y miércoles · mañana",
        group="1",
        capacity=20,
        start_date=today - timedelta(days=45),
        enrollment_fee=Decimal("100.00"),
        monthly_fee=Decimal("200.00"),
    )
    ctx.math = Course.objects.create(
        campus=ctx.central,
        name="Matemática Demo",
        schedule="Martes y jueves · tarde",
        group="2",
        capacity=1,
        start_date=today - timedelta(days=10),
        enrollment_fee=Decimal("80.00"),
        monthly_fee=Decimal("180.00"),
    )
    ctx.old_course = Course.objects.create(
        campus=ctx.central,
        name="Comunicación Demo",
        schedule="Sábado · mañana",
        group="3",
        capacity=15,
        start_date=today - timedelta(days=180),
        enrollment_fee=Decimal("90.00"),
        monthly_fee=Decimal("160.00"),
        active=False,
    )
    ctx.north_course = Course.objects.create(
        campus=ctx.north,
        name="Inglés Demo",
        schedule="Viernes · noche",
        group="1",
        capacity=10,
        start_date=today + timedelta(days=10),
        enrollment_fee=Decimal("100.00"),
        monthly_fee=Decimal("200.00"),
    )


STUDENT_SPECS = (
    # clave, campus, apellidos, nombres, DNI, teléfonos, activo
    ("ana", "central", "Ejemplo", "Ana", "90000001", ("900000001", "900000002"), True),
    ("debtor", "central", "Deuda", "Bruno", "90000002", ("900000003",), True),
    ("no_enrollment", "central", "Sin Matricula", "Carla", "90000003", ("900000004",), True),
    ("inactive", "central", "Inactivo", "Diego", "90000004", ("900000005",), False),
    ("pending", "central", "Pendiente", "Elena", "90000005", ("900000006",), True),
    ("north", "north", "Otra Sede", "Fabio", "90000006", ("900000007",), True),
)


def seed_students(ctx):
    ctx.students = {}
    for key, campus, last_name, first_name, dni, phones, active in STUDENT_SPECS:
        student = Student.objects.create(
            campus=ctx.north if campus == "north" else ctx.central,
            full_name=f"{first_name} {last_name}",
            last_name=last_name,
            first_name=first_name,
            document_number=dni,
            phone=", ".join(phones),
            active=active,
        )
        StudentPhone.objects.bulk_create([StudentPhone(student=student, number=n) for n in phones])
        ctx.students[key] = student


def seed_enrollments(ctx):
    today = ctx.today
    students = ctx.students
    promoter = getattr(ctx, "promoter_main", None)
    ctx.current = Enrollment.objects.create(
        campus=ctx.central,
        student=students["ana"],
        course=ctx.english,
        enrollment_date=today - timedelta(days=40),
        enrollment_fee=Decimal("100.00"),
        monthly_fee=Decimal("200.00"),
    )
    ctx.old = Enrollment.objects.create(
        campus=ctx.central,
        student=students["ana"],
        course=ctx.old_course,
        enrollment_date=today - timedelta(days=200),
        enrollment_fee=Decimal("90.00"),
        monthly_fee=Decimal("160.00"),
        active=False,
    )
    ctx.debt_enrollment = Enrollment.objects.create(
        campus=ctx.central,
        student=students["debtor"],
        course=ctx.math,
        enrollment_date=today - timedelta(days=20),
        enrollment_fee=Decimal("80.00"),
        monthly_fee=Decimal("180.00"),
    )
    if promoter:
        for enrollment in (ctx.current, ctx.old, ctx.debt_enrollment):
            enrollment.promoter.add(promoter)
    # Estudiante sin curso, curso reservado sin estudiante y matrícula de otra sede.
    Enrollment.objects.create(campus=ctx.central, student=students["pending"])
    Enrollment.objects.create(campus=ctx.central, course=ctx.math)
    Enrollment.objects.create(campus=ctx.north, student=students["north"], course=ctx.north_course)


def seed_fichas(ctx):
    for code, enrollment in ((1001, ctx.current), (1002, ctx.old)):
        Ficha.objects.create(
            enrollment=enrollment,
            campus=ctx.central,
            date=enrollment.enrollment_date,
            code=code,
        )
    ctx.current.ficha.image.save("ficha-demo.png", ContentFile(PNG_1X1), save=True)


def seed_installments(ctx):
    today = ctx.today
    current, debt = ctx.current, ctx.debt_enrollment
    specs = (
        ("fee", current, "Matrícula", "100.00", -40),
        ("month_one", current, "Mensualidad 1", "200.00", -10),
        ("month_two", current, "Mensualidad 2 · parcial", "200.00", -1),
        (None, current, "Mensualidad 3 · vencida", "200.00", -30),
        (None, current, "Mensualidad 4 · futura", "200.00", 30),
        (None, debt, "Cuota vencida sin pago", "180.00", -5),
        (None, debt, "Cuota pendiente futura", "180.00", 25),
    )
    ctx.installments = {}
    for key, enrollment, concept, amount, days in specs:
        installment = Installment.objects.create(
            enrollment=enrollment,
            concept=concept,
            amount=Decimal(amount),
            due_date=today + timedelta(days=days),
        )
        if key:
            ctx.installments[key] = installment


def seed_payments(ctx):
    cashier = ctx.users["demo_caja"]
    base = {"campus": ctx.central, "enrollment": ctx.current, "cashier": cashier}
    inst = ctx.installments
    ctx.payment_full = Payment.objects.create(
        receipt_number="D100",
        amount=Decimal("300.00"),
        reference="OPERACION-DEMO-100",
        notes="Pago completo de matrícula y primera cuota.",
        **base,
    )
    PaymentAllocation.objects.create(
        payment=ctx.payment_full, installment=inst["fee"], amount=inst["fee"].amount
    )
    PaymentAllocation.objects.create(
        payment=ctx.payment_full,
        installment=inst["month_one"],
        amount=inst["month_one"].amount,
    )
    partial = Payment.objects.create(
        receipt_number="D101",
        amount=Decimal("75.00"),
        reference="OPERACION-DEMO-101",
        notes="Abono parcial.",
        **base,
    )
    PaymentAllocation.objects.create(
        payment=partial, installment=inst["month_two"], amount=Decimal("75.00")
    )
    void = Payment.objects.create(
        receipt_number="A100",
        amount=Decimal("40.00"),
        notes="Recibo de prueba anulado; se conserva el historial.",
        status=Payment.Status.VOID,
        **base,
    )
    PaymentAllocation.objects.create(
        payment=void, installment=inst["month_two"], amount=Decimal("40.00")
    )
    ctx.payment_full.voucher.save("voucher-demo.png", ContentFile(PNG_1X1), save=True)


def seed_cash_closings(ctx):
    CashClosing.objects.create(
        campus=ctx.central,
        date=ctx.today,
        confirmed_total=Decimal("375.00"),
        voided_total=Decimal("40.00"),
        payments_count=3,
        note="Cierre de caja ficticio para pruebas.",
        closed_by=ctx.users["demo_administrador"],
    )


def seed_call_templates(ctx):
    for kind in WhatsAppTemplate.Kind.values:
        WhatsAppTemplate.objects.create(
            campus=ctx.central, kind=kind, body=WhatsAppTemplate.DEFAULT_BODIES[kind]
        )


def seed_call_assignments(ctx):
    for enrollment in (ctx.current, ctx.debt_enrollment):
        CallAssignment.objects.create(
            user=ctx.users["demo_gestor"],
            enrollment=enrollment,
            assigned_by=ctx.users["demo_asignador"],
        )


def seed_call_notes(ctx):
    for index, (response, label) in enumerate(CallNote.Response.choices):
        promised = response == CallNote.Response.PROMISED_PAYMENT
        CallNote.objects.create(
            campus=ctx.central,
            student=ctx.students["ana"] if index < 3 else ctx.students["debtor"],
            author=ctx.users["demo_gestor"],
            response=response,
            note=f"Nota ficticia de prueba: {label}.",
            promise_date=ctx.today + timedelta(days=index + 1) if promised else None,
        )


def seed_activity(ctx):
    user = ctx.users["demo_matriculas"]
    for object_type, object_id, description in (
        ("student", ctx.students["ana"].pk, "Registró estudiante demo"),
        ("enrollment", ctx.current.pk, "Registró matrícula demo"),
        ("enrollment", ctx.old.pk, "Dio de baja matrícula demo"),
    ):
        ActivityLog.objects.create(
            user=user,
            username=user.username,
            campus=ctx.central,
            action=ActivityLog.Action.CREATE,
            description=description,
            object_type=object_type,
            object_id=object_id,
        )


# Orden topológico: cada elemento solo depende de elementos anteriores.
# clave -> (descripción, dependencias, función)
ELEMENTS = {
    "campuses": ("Sedes (activas e inactiva)", (), seed_campuses),
    "flyers": ("Logo y volante de sede", ("campuses",), seed_flyers),
    "users": ("Usuarios por rol y sus sedes", ("campuses",), seed_users),
    "schedules": ("Horarios", ("campuses",), seed_schedules),
    "promoters": ("Promotores", ("campuses",), seed_promoters),
    "courses": ("Cursos (activos, inactivo, con un solo cupo)", ("campuses",), seed_courses),
    "students": ("Estudiantes y teléfonos (activos e inactivo)", ("campuses",), seed_students),
    "enrollments": (
        "Matrículas (actual, anterior, pendientes, otra sede)",
        ("students", "courses"),
        seed_enrollments,
    ),
    "fichas": ("Fichas de matrícula", ("enrollments",), seed_fichas),
    "installments": (
        "Cuotas (pagadas, parciales, vencidas, futuras)",
        ("enrollments",),
        seed_installments,
    ),
    "payments": (
        "Pagos y recibos (confirmados, anulados, vouchers)",
        ("installments", "users"),
        seed_payments,
    ),
    "cash_closings": ("Cierre de caja", ("payments",), seed_cash_closings),
    "call_templates": ("Plantillas de WhatsApp", ("campuses",), seed_call_templates),
    "call_assignments": (
        "Asignación de llamadas",
        ("enrollments", "users"),
        seed_call_assignments,
    ),
    "call_notes": ("Notas de llamadas", ("students", "users"), seed_call_notes),
    "activity": (
        "Historial de actividad",
        ("students", "enrollments", "users"),
        seed_activity,
    ),
}


def resolve_elements(selected):
    """Añade las dependencias de lo elegido. Devuelve (orden de creación, añadidas)."""
    unknown = [key for key in selected if key not in ELEMENTS]
    if unknown:
        raise CommandError(
            f"Elementos desconocidos: {', '.join(unknown)}. Válidos: {', '.join(ELEMENTS)}."
        )
    needed = set(selected)
    changed = True
    while changed:
        changed = False
        for key in list(needed):
            for dependency in ELEMENTS[key][1]:
                if dependency not in needed:
                    needed.add(dependency)
                    changed = True
    ordered = [key for key in ELEMENTS if key in needed]
    return ordered, [key for key in ordered if key not in selected]


class Command(BaseCommand):
    help = (
        "DESTRUCTIVO: vacía todos los datos y crea datos de demostración. Permite elegir qué "
        "elementos crear; las dependencias necesarias se añaden automáticamente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            help="Elementos separados por comas (ver --list). Sin esta opción se muestra un menú.",
        )
        parser.add_argument("--all", action="store_true", help="Crea todos los elementos.")
        parser.add_argument(
            "--list", action="store_true", help="Muestra los elementos y sus dependencias."
        )

    def print_catalog(self):
        self.stdout.write("Elementos disponibles (clave · descripción · requiere):")
        for number, (key, (label, requires, _)) in enumerate(ELEMENTS.items(), start=1):
            needs = ", ".join(requires) or "—"
            self.stdout.write(f"  {number:>2}. {key:<17} {label}  [requiere: {needs}]")

    def choose_elements(self, options):
        if options["all"]:
            return list(ELEMENTS)
        if options["only"]:
            return [key.strip() for key in options["only"].split(",") if key.strip()]
        self.print_catalog()
        answer = input(
            "Números o claves separados por coma (Enter = todo; las dependencias se añaden): "
        ).strip()
        if not answer:
            return list(ELEMENTS)
        keys = list(ELEMENTS)
        chosen = []
        for token in (part.strip() for part in answer.split(",") if part.strip()):
            if token.isdigit() and 1 <= int(token) <= len(keys):
                chosen.append(keys[int(token) - 1])
            else:
                chosen.append(token)
        return chosen

    def handle(self, *args, **options):
        if options["list"]:
            self.print_catalog()
            return
        if not sys.stdin.isatty():
            raise CommandError("Se necesita una terminal interactiva (use docker exec -it).")

        selected = self.choose_elements(options)
        if not selected:
            raise CommandError("No se eligió ningún elemento.")
        ordered, added = resolve_elements(selected)
        if "users" in ordered:
            roles = set(ROLE_USERS.values())
            existing = set(Group.objects.filter(name__in=roles).values_list("name", flat=True))
            if roles - existing:
                raise CommandError(
                    "Faltan grupos de roles. Ejecuta primero las migraciones: "
                    + ", ".join(sorted(roles - existing))
                )

        if added:
            self.stdout.write(
                "Se añadieron por dependencia: "
                + ", ".join(f"{key} ({ELEMENTS[key][0]})" for key in added)
            )
        self.stdout.write("Se crearán: " + ", ".join(ordered) + ".")
        self.stdout.write(
            self.style.WARNING(
                f"Se vaciarán {len(tables_to_wipe())} tablas y se borrarán todos los archivos "
                "subidos antes de crear los datos. Los grupos, permisos y migraciones se "
                "conservan.\nEsta acción NO se puede deshacer. Haz un respaldo antes de continuar."
            )
        )
        if input(f"Escribe «{CONFIRMATION}» para continuar: ").strip() != CONFIRMATION:
            self.stdout.write("Cancelado. No se modificó nada.")
            return

        password = self.ask_password()
        with transaction.atomic():
            flush_database()
            wipe_media()
            ctx = self.create(ordered, password)
        cache.clear()

        self.stdout.write(self.style.SUCCESS("Datos de demostración creados."))
        for label, model in (
            ("sedes", Campus),
            ("usuarios", get_user_model()),
            ("cursos", Course),
            ("estudiantes", Student),
            ("matrículas", Enrollment),
            ("cuotas", Installment),
            ("pagos", Payment),
            ("llamadas", CallNote),
        ):
            self.stdout.write(f"  {label}: {model.objects.count()}")
        self.stdout.write(f"Cuentas (contraseña ingresada): {ADMIN_USERNAME} (superusuario)")
        for username in getattr(ctx, "users", {}):
            self.stdout.write(f"  {username}")

    def create(self, ordered, password):
        User = get_user_model()
        ctx = SimpleNamespace(today=timezone.localdate(), password=password)
        ctx.admin = User.objects.create_superuser(
            username=ADMIN_USERNAME, email="", password=password
        )
        for key in ordered:
            ELEMENTS[key][2](ctx)
        return ctx

    def ask_password(self):
        User = get_user_model()
        while True:
            password = getpass.getpass("Contraseña común para las cuentas demo: ")
            if password != getpass.getpass("Repite la contraseña: "):
                self.stderr.write("Las contraseñas no coinciden.")
                continue
            try:
                validate_password(password, User(username=ADMIN_USERNAME))
            except ValidationError as error:
                for message in error.messages:
                    self.stderr.write(message)
                continue
            return password
