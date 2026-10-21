"""Guía visual de primer ingreso: recorrido por las vistas y qué puede o no hacer cada usuario."""

from django.urls import reverse

# (icono, título, permisos [basta uno], qué puede hacer, qué no puede hacer)
CAPABILITIES = [
    (
        "school",
        "Consultar estudiantes",
        ("students.view_student",),
        "Buscar estudiantes y abrir su ficha integral.",
        "No puedes consultar la lista ni las fichas de estudiantes.",
    ),
    (
        "person_add",
        "Registrar estudiantes",
        ("students.add_student",),
        "Registrar estudiantes nuevos e importarlos desde Excel.",
        "No puedes registrar estudiantes nuevos.",
    ),
    (
        "assignment",
        "Matricular",
        ("students.add_enrollment",),
        "Crear matrículas y consultar las existentes.",
        "No puedes crear matrículas.",
    ),
    (
        "swap_horiz",
        "Cambiar o dar de baja matrículas",
        ("core.change_enrollment_course", "core.deactivate_enrollment", "core.deactivate_student"),
        "Cambiar el curso de una matrícula y dar de baja estudiantes o matrículas.",
        "No puedes cambiar el curso ni dar de baja estudiantes o matrículas.",
    ),
    (
        "menu_book",
        "Cursos y promotores",
        ("students.add_course", "students.add_promoter"),
        "Crear y editar cursos, horarios y promotores de la sede.",
        "No puedes crear ni editar cursos o promotores; solo consultarlos si tienes acceso.",
    ),
    (
        "payments",
        "Registrar pagos",
        ("payments.add_payment",),
        "Cobrar cuotas y emitir recibos.",
        "No puedes registrar pagos.",
    ),
    (
        "money_off",
        "Cuotas y saldos pendientes",
        ("core.view_pending_balances",),
        "Consultar cuotas, deudas y saldos pendientes.",
        "No puedes consultar cuotas ni saldos pendientes.",
    ),
    (
        "block",
        "Anular pagos",
        ("core.void_payment",),
        "Anular un pago; el recibo y su historial se conservan.",
        "No puedes anular pagos.",
    ),
    (
        "point_of_sale",
        "Cerrar la caja",
        ("core.close_cash",),
        "Cerrar la caja de una fecha.",
        "No puedes cerrar la caja.",
    ),
    (
        "phone_in_talk",
        "Registrar llamadas",
        ("calls.add_callnote",),
        "Registrar llamadas, promesas de pago y mensajes de WhatsApp.",
        "No puedes registrar llamadas de seguimiento.",
    ),
    (
        "assignment_ind",
        "Asignar llamadas",
        ("core.assign_calls",),
        "Armar sublistas de matrículas y asignarlas a varios gestores.",
        "No puedes asignar llamadas a otros usuarios.",
    ),
    (
        "assessment",
        "Informes",
        (
            "core.view_academic_reports",
            "core.view_financial_reports",
            "core.view_call_reports",
        ),
        "Consultar los informes de tu área.",
        "No puedes consultar informes.",
    ),
    (
        "download",
        "Exportar a Excel",
        ("core.export_reports",),
        "Descargar listados e informes en Excel.",
        "No puedes exportar datos a Excel.",
    ),
    (
        "apartment",
        "Sedes y usuarios",
        ("core.manage_user_access", "core.add_campus", "core.change_campus"),
        "Administrar usuarios, grupos de acceso y sedes.",
        "No puedes administrar usuarios, grupos ni sedes.",
    ),
]


def _view(url_name, icon, title, summary, actions, any_of=(), all_of=(), superuser=False):
    return {
        "url_name": url_name,
        "icon": icon,
        "title": title,
        "summary": summary,
        "actions": actions,
        "any_of": any_of,
        "all_of": all_of,
        "superuser": superuser,
    }


# Vistas del menú lateral, en su orden. Cada acción [texto, permiso] solo se muestra si el usuario
# tiene el permiso (None = siempre). El enlace se localiza en el menú por su URL.
TOUR = [
    _view(
        "dashboard",
        "dashboard",
        "Panel principal",
        "Tu punto de partida: un resumen de la sede seleccionada.",
        [["Ver los indicadores y accesos rápidos de la sede.", None]],
    ),
    _view(
        "student-list",
        "school",
        "Estudiantes",
        "Lista de los estudiantes de la sede.",
        [
            ["Buscar por nombre, DNI o teléfono.", None],
            ["Abrir la ficha integral: datos, matrículas, pagos e historial.", None],
            ["Registrar un estudiante con el botón «+ Nuevo estudiante».", "students.add_student"],
            ["Editar sus datos y teléfonos.", "students.change_student"],
            ["Dar de baja a un estudiante conservando su historial.", "core.deactivate_student"],
        ],
        any_of=("students.view_student",),
    ),
    _view(
        "course-list",
        "menu_book",
        "Cursos",
        "Cursos de la sede con su horario, grupo, fecha de inicio, capacidad y costos.",
        [
            ["Consultar los cursos y sus vacantes.", None],
            ["Crear un curso con el botón «+ Nuevo curso».", "students.add_course"],
            ["Editar la fecha de inicio, la capacidad y los costos.", "students.change_course"],
        ],
        any_of=("students.view_course",),
    ),
    _view(
        "enrollment-list",
        "assignment",
        "Matrículas",
        "Inscripciones de estudiantes en cursos. Las que se hicieron con el curso ya iniciado "
        "llevan la etiqueta «Incorporación».",
        [
            ["Filtrar y consultar matrículas.", None],
            ["Crear una matrícula nueva.", "students.add_enrollment"],
            ["Cambiar el curso de una matrícula.", "core.change_enrollment_course"],
            ["Dar de baja una matrícula conservando su historial.", "core.deactivate_enrollment"],
            ["Exportar el listado a Excel.", "core.export_reports"],
        ],
        any_of=("students.view_enrollment",),
    ),
    _view(
        "promoter-list",
        "badge",
        "Promotores",
        "Promotores disponibles en la sede.",
        [
            ["Consultar los promotores.", None],
            ["Crear un promotor con el botón «+ Nuevo promotor».", "students.add_promoter"],
        ],
        any_of=("students.view_promoter",),
    ),
    _view(
        "student-import",
        "upload_file",
        "Importar Excel",
        "Carga masiva de estudiantes desde una hoja de cálculo.",
        [["Subir un archivo de Excel y registrar varios estudiantes a la vez.", None]],
        any_of=("students.add_student",),
    ),
    _view(
        "student-duplicates",
        "merge_type",
        "Duplicados",
        "Detecta estudiantes repetidos.",
        [["Revisar posibles duplicados y fusionarlos.", None]],
        all_of=("core.deactivate_student", "students.change_student"),
    ),
    _view(
        "trash",
        "delete_sweep",
        "Papelera",
        "Estudiantes y matrículas dados de baja.",
        [["Consultarlos y restaurarlos cuando corresponda.", None]],
        any_of=("core.deactivate_student", "core.deactivate_enrollment"),
    ),
    _view(
        "payment-list",
        "receipt_long",
        "Pagos",
        "Pagos y recibos emitidos en la sede.",
        [
            ["Buscar y consultar recibos.", None],
            ["Registrar un pago con el botón de nuevo pago.", "payments.add_payment"],
            ["Editar un recibo (hasta que se cierre la caja).", "payments.change_payment"],
            ["Anular un pago; el recibo y su historial se conservan.", "core.void_payment"],
            ["Exportar los pagos a Excel.", "core.export_reports"],
        ],
        any_of=("payments.view_payment",),
    ),
    _view(
        "payment-create",
        "payments",
        "Registrar pago",
        "Cobra cuotas de una matrícula y emite el recibo.",
        [
            ["Elegir al estudiante y la matrícula.", None],
            ["Registrar pagos parciales: el importe se reparte entre las cuotas pendientes.", None],
        ],
        any_of=("payments.add_payment",),
    ),
    _view(
        "installment-list",
        "event_note",
        "Cuotas",
        "Cuotas de las matrículas con su vencimiento y estado.",
        [
            ["Consultar cuotas y ver cuáles están vencidas.", None],
            ["Ir a cobrar una cuota.", "payments.add_payment"],
        ],
        any_of=("core.view_pending_balances",),
    ),
    _view(
        "pending-debts",
        "money_off",
        "Saldos pendientes",
        "Deuda pendiente de cada estudiante, para la cobranza.",
        [
            ["Ver quién debe y cuánto.", None],
            ["Exportar los saldos a Excel.", "core.export_reports"],
        ],
        any_of=("core.view_pending_balances",),
    ),
    _view(
        "calls-assignments",
        "assignment_ind",
        "Asignar llamadas",
        "Organiza las matrículas en sublistas y asígnalas a los gestores de llamadas.",
        [
            ["Filtrar y seleccionar matrículas para crear sublistas.", None],
            ["Asignar varios gestores a una sublista.", None],
            ["Administrar las sublistas existentes y sus integrantes.", None],
        ],
        any_of=("core.assign_calls",),
    ),
    _view(
        "calls-queue",
        "phone_forwarded",
        "Pedir llamada",
        "Cola de llamadas de tu sublista, al estilo call center.",
        [
            ["Pedir el siguiente alumno por llamar.", None],
            ["Ver a quién está llamando el resto de tu sublista.", None],
            ["Registrar el resultado o liberar al alumno.", None],
        ],
        any_of=("calls.add_callnote",),
    ),
    _view(
        "calls-notes-all",
        "forum",
        "Historial de llamadas",
        "Todas las notas de llamadas registradas.",
        [
            ["Consultar y filtrar el historial.", None],
            ["Editar notas existentes.", "core.edit_call_notes"],
        ],
        any_of=("calls.view_callnote",),
    ),
    _view(
        "calls-report",
        "assessment",
        "Reporte de llamadas",
        "Resumen de la actividad de llamadas.",
        [["Consultar el rendimiento de llamadas por periodo.", None]],
        any_of=("core.view_call_reports",),
    ),
    _view(
        "course-student-tables",
        "groups",
        "Ocupación por curso",
        "Vacantes y estudiantes de cada curso, en una sola pantalla.",
        [
            ["Ver cupos ocupados y libres por curso.", None],
            ["Listar los alumnos de cada curso.", None],
            ["Exportar a Excel.", "core.export_reports"],
        ],
        any_of=("core.view_academic_reports",),
    ),
    _view(
        "report-pending-course",
        "pending_actions",
        "Pendientes de curso",
        "Matrículas que aún no tienen un curso asignado.",
        [["Identificar qué matrículas falta completar.", None]],
        any_of=("core.view_academic_reports",),
    ),
    _view(
        "report-enrollments-by-month",
        "calendar_month",
        "Matrículas por mes",
        "Evolución mensual de las matrículas.",
        [["Comparar cuántas matrículas se hicieron cada mes.", None]],
        any_of=("core.view_academic_reports",),
    ),
    _view(
        "report-enrollments-by-promoter",
        "badge",
        "Matrículas por promotor",
        "Matrículas logradas por cada promotor.",
        [["Medir el aporte de cada promotor.", None]],
        any_of=("core.view_academic_reports",),
    ),
    _view(
        "report-debt-by-course",
        "trending_down",
        "Morosidad por curso",
        "Deuda pendiente agrupada por curso.",
        [["Ver en qué cursos se concentra la deuda.", None]],
        any_of=("core.view_pending_balances",),
    ),
    _view(
        "report-income-by-month",
        "savings",
        "Ingresos por mes",
        "Ingresos cobrados cada mes.",
        [["Consultar el dinero recibido por periodo.", None]],
        any_of=("core.view_financial_reports",),
    ),
    _view(
        "cash-closing",
        "point_of_sale",
        "Cierre de caja",
        "Resumen de lo cobrado en un día.",
        [
            ["Revisar los cobros de una fecha.", None],
            [
                "Cerrar la caja; después no se pueden editar ni anular pagos de esa fecha.",
                "core.close_cash",
            ],
        ],
        any_of=("core.view_financial_reports",),
        all_of=("payments.view_payment",),
    ),
    _view(
        "tools",
        "build",
        "Herramientas",
        "Utilidades de apoyo para matrícula y caja.",
        [["Usar las utilidades disponibles para tu rol.", None]],
        any_of=("students.add_enrollment", "payments.add_payment"),
    ),
    _view(
        "campus-list",
        "apartment",
        "Sedes",
        "Sedes (campus) del instituto.",
        [
            ["Consultar las sedes.", None],
            ["Crear una sede nueva.", "core.add_campus"],
            ["Editar sus datos, logo y volantes.", "core.change_campus"],
        ],
        any_of=("core.view_campus",),
    ),
    _view(
        "user-list",
        "group",
        "Usuarios",
        "Cuentas de acceso al sistema.",
        [
            ["Consultar los usuarios.", None],
            ["Crear y editar usuarios, sus grupos y sus sedes.", "core.manage_user_access"],
        ],
        any_of=("core.view_user",),
    ),
    _view(
        "activity-log",
        "history",
        "Actividad",
        "Bitácora de lo que hace cada usuario.",
        [["Auditar quién hizo qué y cuándo.", None]],
        superuser=True,
    ),
]


def build_tour(user):
    """Vistas del menú que el usuario puede abrir, con lo que puede hacer en cada una."""
    steps = []
    for view in TOUR:
        if view["superuser"] and not user.is_superuser:
            continue
        if not user.is_superuser:
            if view["any_of"] and not any(user.has_perm(perm) for perm in view["any_of"]):
                continue
            if not all(user.has_perm(perm) for perm in view["all_of"]):
                continue
        actions = [text for text, perm in view["actions"] if perm is None or user.has_perm(perm)]
        steps.append(
            {
                "url": reverse(view["url_name"]),
                "icon": view["icon"],
                "title": view["title"],
                "summary": view["summary"],
                "actions": actions,
            }
        )
    return steps


def build_guide(user, *, pending):
    can, cannot = [], []
    for icon, title, perms, allowed, denied in CAPABILITIES:
        if user.is_superuser or any(user.has_perm(perm) for perm in perms):
            can.append({"icon": icon, "title": title, "text": allowed})
        else:
            cannot.append({"icon": icon, "title": title, "text": denied})
    if user.is_superuser:
        role = "Superusuario"
    else:
        role = ", ".join(user.groups.order_by("name").values_list("name", flat=True))
    return {
        "pending": pending,
        "role": role or "Permisos asignados individualmente",
        "can": can,
        "cannot": cannot,
        "is_superuser": user.is_superuser,
        "tour": build_tour(user),
    }
