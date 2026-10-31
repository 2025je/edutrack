"""Descripción en español de los permisos: módulo, nombre y acciones que habilita."""

MODULES = {
    "students": "Estudiantes, cursos y matrículas",
    "payments": "Caja y pagos",
    "calls": "Seguimiento de llamadas",
    "core": "Sistema y reportes",
    "auth": "Usuarios, grupos y permisos",
}

# Sustantivos por modelo: (singular, plural).
NOUNS = {
    "students.student": ("estudiante", "estudiantes"),
    "students.studentphone": ("teléfono de estudiante", "teléfonos de estudiantes"),
    "students.course": ("curso", "cursos"),
    "students.schedule": ("horario", "horarios"),
    "students.promoter": ("promotor", "promotores"),
    "students.enrollment": ("matrícula", "matrículas"),
    "students.ficha": ("ficha", "fichas"),
    "students.desktoprecordidentity": (
        "vínculo de identidad local de Desktop",
        "vínculos de identidad local de Desktop",
    ),
    "payments.payment": ("pago", "pagos"),
    "payments.cashclosing": ("cierre de caja", "cierres de caja"),
    "payments.installment": ("cuota", "cuotas"),
    "payments.paymentallocation": ("aplicación de pago", "aplicaciones de pago"),
    "calls.callnote": ("llamada", "llamadas"),
    "calls.callclaim": ("llamada en curso", "llamadas en curso"),
    "calls.whatsappsend": ("marca de WhatsApp", "marcas de WhatsApp"),
    "calls.calllist": ("sublista de llamadas", "sublistas de llamadas"),
    "calls.calllistmember": ("usuario de sublista", "usuarios de sublistas"),
    "calls.whatsapptemplate": ("plantilla de WhatsApp", "plantillas de WhatsApp"),
    "core.user": ("usuario", "usuarios"),
    "core.campus": ("sede", "sedes"),
    "core.campusflyer": ("volante de sede", "volantes de sedes"),
    "core.activitylog": ("registro de actividad", "registros de actividad"),
    "auth.group": ("grupo", "grupos"),
    "auth.permission": ("permiso", "permisos"),
}

VERBS = {
    "view": "Consultar",
    "add": "Registrar",
    "change": "Editar",
    "delete": "Eliminar",
}

# Detalle de lo que permite cada acción estándar (cuando aporta más que el nombre).
DETAILS = {
    "students.view_student": "Ver la lista de estudiantes y sus datos de contacto.",
    "students.add_student": "Crear nuevos estudiantes desde el formulario de registro.",
    "students.change_student": "Corregir los datos de un estudiante existente.",
    "students.delete_student": "Eliminar definitivamente un estudiante. Se recomienda usar la baja.",
    "students.view_course": "Ver los cursos del campus, sus costos y horarios.",
    "students.add_course": "Crear cursos nuevos.",
    "students.change_course": "Editar cursos existentes (nombre, costos, horarios).",
    "students.view_enrollment": "Ver las matrículas, sus costos, promotores y fichas.",
    "students.add_enrollment": "Matricular a un estudiante en un curso.",
    "students.change_enrollment": "Editar los datos de una matrícula (promotor, ficha, costos).",
    "students.delete_enrollment": "Eliminar definitivamente una matrícula.",
    "students.view_promoter": "Ver la lista de promotores.",
    "students.add_promoter": "Registrar promotores nuevos.",
    "students.change_promoter": "Editar los datos de un promotor.",
    "payments.view_payment": "Ver los pagos y recibos registrados.",
    "payments.add_payment": "Registrar pagos y generar su recibo.",
    "payments.change_payment": "Corregir los datos de un pago ya registrado.",
    "payments.delete_payment": "Eliminar definitivamente un pago.",
    "payments.view_installment": "Ver las cuotas de las matrículas.",
    "calls.view_callnote": "Ver las llamadas asignadas y su historial de notas.",
    "calls.add_callnote": "Registrar el resultado de una llamada y sus notas; usar la plantilla de WhatsApp.",
    "calls.change_callnote": "Editar el contenido de una llamada registrada.",
    "calls.delete_callnote": "Eliminar una llamada del historial.",
    "core.view_user": "Ver la lista de usuarios del sistema.",
    "core.view_campus": "Ver las sedes del instituto.",
    "core.add_campus": "Crear sedes nuevas.",
    "core.change_campus": "Editar sedes, su logo y sus volantes.",
    "auth.view_group": "Ver los grupos (roles) y los permisos de cada uno.",
    "auth.add_group": "Crear grupos nuevos.",
    "auth.change_group": "Modificar los permisos de un grupo.",
    "auth.view_permission": "Ver el catálogo de permisos disponibles.",
}

# Permisos especiales: (nombre, qué permite).
SPECIAL = {
    "core.deactivate_student": (
        "Dar de baja estudiantes",
        "Desactivar un estudiante conservando sus matrículas, pagos y recibos.",
    ),
    "core.deactivate_enrollment": (
        "Dar de baja matrículas",
        "Desactivar una matrícula conservando su historial de pagos.",
    ),
    "core.change_enrollment_course": (
        "Cambiar el curso de una matrícula",
        "Cambiar el curso asociado a una matrícula existente.",
    ),
    "core.void_payment": (
        "Anular pagos",
        "Anular un pago conservando su historial y su recibo.",
    ),
    "core.edit_call_notes": (
        "Editar notas de llamadas",
        "Modificar las notas de llamadas ya registradas.",
    ),
    "core.assign_calls": (
        "Asignar llamadas",
        "Distribuir llamadas a los gestores y ver las asignaciones.",
    ),
    "core.view_all_calls": (
        "Ver todas las llamadas del campus",
        "Consultar las llamadas de todos los gestores, no solo las propias.",
    ),
    "core.view_financial_reports": (
        "Ver reportes financieros",
        "Consultar los reportes de pagos, recibos y deudas.",
    ),
    "core.view_pending_balances": (
        "Ver cuotas y saldos pendientes",
        "Consultar las cuotas por cobrar y las deudas pendientes por matrícula.",
    ),
    "core.view_academic_reports": (
        "Ver reportes académicos",
        "Consultar los alumnos por curso, grupo y horario.",
    ),
    "core.view_call_reports": (
        "Ver reportes de llamadas",
        "Consultar el reporte de llamadas por usuario y resultado.",
    ),
    "core.close_cash": (
        "Cerrar la caja del día",
        "Firmar el cierre de caja de una fecha; después nadie puede editar ni anular sus pagos.",
    ),
    "core.export_reports": (
        "Exportar a Excel",
        "Descargar a Excel los reportes y listados a los que tengas acceso.",
    ),
    "core.manage_user_access": (
        "Administrar accesos",
        "Crear y editar usuarios, y asignarles grupos y sedes.",
    ),
}


def describe(perm):
    """Devuelve (módulo, nombre, detalle) en español para un objeto Permission."""
    app = perm.content_type.app_label
    key = f"{app}.{perm.codename}"
    module = MODULES.get(app, app.title())
    if key in SPECIAL:
        name, detail = SPECIAL[key]
        return module, name, detail

    action, _, model = perm.codename.partition("_")
    nouns = NOUNS.get(f"{app}.{model}")
    if action in VERBS and nouns:
        name = f"{VERBS[action]} {nouns[1]}"
        default = f"{VERBS[action]} {nouns[1]} del sistema."
        return module, name, DETAILS.get(key, default)
    return module, perm.name, DETAILS.get(key, "")
