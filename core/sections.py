import unicodedata

from django.urls import reverse

ACADEMIC = ("core.view_academic_reports",)
DEBTS = ("core.view_pending_balances",)
CALLS = ("calls.view_callnote",)


def entry(group, name, url_name, perms=(), keywords="", query="", superuser=False):
    return {
        "group": group,
        "name": name,
        "url_name": url_name,
        "perms": perms,
        "keywords": keywords,
        "query": query,
        "superuser": superuser,
    }


# Secciones, subsecciones, filtros rápidos y acciones de la app (no registros).
SECTIONS = [
    entry("General", "Panel principal", "dashboard", keywords="inicio resumen estadisticas"),
    entry("General", "Mi perfil", "profile", keywords="cuenta contraseña clave usuario"),
    entry("Académico", "Estudiantes", "student-list", ("students.view_student",), "alumnos lista"),
    entry(
        "Académico",
        "Nuevo estudiante",
        "student-create",
        ("students.add_student",),
        "registrar alumno",
    ),
    entry(
        "Académico",
        "Importar desde Excel",
        "student-import",
        ("students.add_student",),
        "cargar subir xlsx",
    ),
    entry(
        "Académico",
        "Duplicados",
        "student-duplicates",
        ("core.deactivate_student", "students.change_student"),
        "fusionar repetidos",
    ),
    entry(
        "Académico",
        "Papelera",
        "trash",
        ("core.deactivate_student",),
        "eliminados restaurar desactivados",
    ),
    entry(
        "Académico",
        "Cursos",
        "course-list",
        ("students.view_course",),
        "talleres horarios vacantes",
    ),
    entry(
        "Académico", "Nuevo curso", "course-list", ("students.add_course",), "crear taller agregar"
    ),
    entry("Académico", "Nuevo horario", "schedule-create", ("students.add_course",), "crear turno"),
    entry(
        "Académico",
        "Matrículas",
        "enrollment-list",
        ("students.view_enrollment",),
        "inscripciones fichas",
    ),
    entry(
        "Académico",
        "Nueva matrícula",
        "enrollment-create",
        ("students.add_enrollment",),
        "inscribir",
    ),
    entry(
        "Académico",
        "Exportar matrículas a Excel",
        "enrollment-excel",
        ("students.view_enrollment", "core.export_reports"),
        "descargar xlsx",
    ),
    entry("Académico", "Promotores", "promoter-list", ("students.view_promoter",), "vendedores"),
    entry("Caja", "Pagos", "payment-list", ("payments.view_payment",), "recibos cobros"),
    entry(
        "Caja", "Registrar pago", "payment-create", ("payments.add_payment",), "cobrar recibo nuevo"
    ),
    entry(
        "Caja",
        "Exportar pagos a Excel",
        "payment-excel",
        ("payments.view_payment", "core.export_reports"),
        "descargar xlsx recibos",
    ),
    entry("Caja", "Cuotas", "installment-list", DEBTS, "mensualidades vencimientos"),
    entry("Caja", "Cuotas vencidas", "installment-list", DEBTS, "atrasadas mora", "?vencidas=1"),
    entry("Caja", "Saldos pendientes", "pending-debts", DEBTS, "deudas morosos cobranza"),
    entry(
        "Caja",
        "Exportar saldos pendientes a Excel",
        "pending-debts-excel",
        DEBTS + ("core.export_reports",),
        "descargar xlsx deudas",
    ),
    entry(
        "Caja",
        "Cierre de caja",
        "cash-closing",
        ("payments.view_payment", "core.view_financial_reports"),
        "arqueo cajero cerrar firmar",
    ),
    entry("Llamadas", "Seguimiento de llamadas", "calls-students", CALLS, "cobranza whatsapp"),
    entry(
        "Llamadas",
        "Llamar hoy (promesas de pago)",
        "calls-students",
        CALLS,
        "promesas vencen hoy mañana recordatorio",
        "?promesa=hoy",
    ),
    entry(
        "Llamadas",
        "Promesas incumplidas",
        "calls-students",
        CALLS,
        "vencidas promesa pago",
        "?promesa=vencida",
    ),
    entry("Llamadas", "Historial de llamadas", "calls-notes-all", CALLS, "notas"),
    entry(
        "Llamadas", "Reporte de llamadas", "calls-report", ("core.view_call_reports",), "informe"
    ),
    entry(
        "Llamadas",
        "Asignar llamadas",
        "calls-assignments",
        ("core.assign_calls",),
        "repartir gestor",
    ),
    entry(
        "Llamadas",
        "Plantilla de WhatsApp: deuda vencida",
        "calls-template",
        ("calls.add_callnote",),
        "mensaje texto",
        "?tipo=DEUDA",
    ),
    entry(
        "Llamadas",
        "Plantilla de WhatsApp: promesa incumplida",
        "calls-template",
        ("calls.add_callnote",),
        "mensaje texto",
        "?tipo=PROMESA",
    ),
    entry(
        "Llamadas",
        "Plantilla de WhatsApp: bienvenida",
        "calls-template",
        ("calls.add_callnote",),
        "mensaje texto",
        "?tipo=BIENVENIDA",
    ),
    entry(
        "Informes",
        "Ocupación por curso",
        "course-student-tables",
        ACADEMIC,
        "listas asistencia vacantes cupos",
    ),
    entry(
        "Informes", "Pendientes de curso", "report-pending-course", ACADEMIC, "matricula sin curso"
    ),
    entry("Informes", "Matrículas por mes", "report-enrollments-by-month", ACADEMIC),
    entry("Informes", "Matrículas por promotor", "report-enrollments-by-promoter", ACADEMIC),
    entry("Informes", "Morosidad por curso", "report-debt-by-course", DEBTS, "deuda"),
    entry(
        "Informes",
        "Ingresos por mes",
        "report-income-by-month",
        ("core.view_financial_reports",),
        "ventas dinero",
    ),
    entry("Informes", "Herramientas", "tools", ("students.add_enrollment",), "utilidades"),
    entry("Sistema", "Sedes", "campus-list", ("core.view_campus",), "campus"),
    entry("Sistema", "Nueva sede", "campus-create", ("core.add_campus",), "crear campus agregar"),
    entry(
        "Sistema", "Usuarios", "user-list", ("core.view_user",), "cuentas accesos roles permisos"
    ),
    entry(
        "Sistema",
        "Nuevo usuario",
        "user-create",
        ("core.manage_user_access",),
        "crear cuenta agregar",
    ),
    entry(
        "Sistema",
        "Actividad",
        "activity-log",
        keywords="bitacora auditoria registro",
        superuser=True,
    ),
]


def plain(text):
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_sections(user, query):
    """Secciones, subsecciones y acciones permitidas al usuario que contienen todas las palabras."""
    words = plain(query).split()
    found = []
    for item in SECTIONS:
        if item["superuser"] and not user.is_superuser:
            continue
        if not all(user.has_perm(perm) for perm in item["perms"]):
            continue
        haystack = plain(f"{item['name']} {item['group']} {item['keywords']}")
        if all(word in haystack for word in words):
            found.append(
                {
                    "group": item["group"],
                    "name": item["name"],
                    "url": reverse(item["url_name"]) + item["query"],
                }
            )
    return found
