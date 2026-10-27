import secrets

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from core.campus import FeaturePermissionMixin, SelectedCampusRequiredMixin, get_selected_campus
from core.models import Campus

from .offline_sync import (
    MAX_PACKAGE_BYTES,
    OfflinePackageError,
    export_campus,
    import_initial_package,
    import_package,
    package_bytes,
    parse_package,
    review_courses,
    review_package,
)

CACHE_KEY_PREFIX = "desktop-offline-import"
SESSION_TOKEN_KEY = "desktop_offline_import_token"
PREVIEW_TTL_SECONDS = 600


class DesktopPermissionMixin(FeaturePermissionMixin):
    required_permission = ("students.add_student", "students.add_enrollment")


class SelectedCampusOrCreatePermissionMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if get_selected_campus(request) is None and not request.user.has_perm("core.add_campus"):
            return redirect("select-campus")
        return super().dispatch(request, *args, **kwargs)


class OfflineCampusExportView(DesktopPermissionMixin, SelectedCampusRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        campus = get_selected_campus(request)
        try:
            manifest, attachments = export_campus(campus)
            payload = package_bytes(manifest, attachments)
        except OfflinePackageError as exc:
            messages.error(request, str(exc))
            return redirect("desktop-import")
        response = HttpResponse(payload, content_type="application/vnd.edutrack.offline+zip")
        response["Content-Disposition"] = (
            f'attachment; filename="edutrack-sede-{campus.pk}.edutrack"'
        )
        return response


class DesktopOfflineImportView(
    DesktopPermissionMixin, SelectedCampusOrCreatePermissionMixin, TemplateView
):
    template_name = "students/desktop_import.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_campus"] = get_selected_campus(self.request)
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "preview":
            return self.preview(request)
        if action == "confirm":
            return self.confirm(request)
        messages.error(request, "Acción de sincronización no válida.")
        return redirect("desktop-import")

    def preview(self, request):
        upload = request.FILES.get("package")
        if not upload or not upload.name.lower().endswith((".edutrack", ".zip")):
            messages.error(
                request, "Selecciona un archivo de sincronización EduTrack (.edutrack o .zip)."
            )
            return redirect("desktop-import")
        if upload.size > MAX_PACKAGE_BYTES:
            messages.error(request, "El archivo supera el tamaño máximo de 25 MB.")
            return redirect("desktop-import")
        payload = upload.read(MAX_PACKAGE_BYTES + 1)
        if len(payload) > MAX_PACKAGE_BYTES:
            messages.error(request, "El archivo supera el tamaño máximo de 25 MB.")
            return redirect("desktop-import")
        try:
            package = parse_package(payload)
            campus = get_selected_campus(request)
            course_rows = []
            if package["campus_mode"] == "new":
                if not request.user.has_perm("core.add_campus"):
                    raise OfflinePackageError("No tienes permiso para crear una sede nueva.")
                if Campus.objects.filter(desktop_bundle_id=package["bundle_id"]).exists():
                    raise OfflinePackageError("Este paquete inicial ya fue importado.")
                if Campus.objects.filter(name__iexact=package["campus_name"]).exists():
                    raise OfflinePackageError("Ya existe una sede con ese nombre.")
                student_rows, enrollment_rows = self.initial_rows(package)
            else:
                if campus is None:
                    raise OfflinePackageError("Selecciona una sede antes de sincronizar.")
                student_rows, enrollment_rows = review_package(package, campus)
                course_rows, _ = review_courses(package, campus)
                self.enforce_change_permissions(
                    request, student_rows, enrollment_rows, course_rows, package
                )
        except OfflinePackageError as exc:
            messages.error(request, str(exc))
            return redirect("desktop-import")

        old_token = request.session.pop(SESSION_TOKEN_KEY, None)
        if old_token:
            cache.delete(self.cache_key(request, old_token))
        token = secrets.token_urlsafe(24)
        cache.set(
            self.cache_key(request, token),
            {
                "payload": payload,
                "campus_id": (
                    campus.pk if campus and package["campus_mode"] == "existing" else None
                ),
                "campus_mode": package["campus_mode"],
            },
            timeout=PREVIEW_TTL_SECONDS,
        )
        request.session[SESSION_TOKEN_KEY] = token
        return self.render_preview(
            request, package, student_rows, enrollment_rows, token, course_rows
        )

    def confirm(self, request):
        token = request.POST.get("token", "")
        session_token = request.session.get(SESSION_TOKEN_KEY, "")
        if not token or not secrets.compare_digest(token, session_token):
            messages.error(request, "La vista previa venció o no pertenece a esta sesión.")
            return redirect("desktop-import")
        cached = cache.get(self.cache_key(request, token))
        if not cached:
            request.session.pop(SESSION_TOKEN_KEY, None)
            messages.error(request, "La vista previa venció. Sube el archivo otra vez.")
            return redirect("desktop-import")
        try:
            package = parse_package(cached["payload"])
            if package["campus_mode"] == "new":
                if cached["campus_mode"] != "new":
                    raise OfflinePackageError("El paquete de la vista previa cambió.")
                campus, counts = import_initial_package(package, request)
                student_rows, enrollment_rows = self.initial_rows(package)
                cache.delete(self.cache_key(request, token))
                request.session.pop(SESSION_TOKEN_KEY, None)
                return self.render_result(
                    package,
                    student_rows,
                    enrollment_rows,
                    counts,
                    campus,
                    initial=True,
                )
            campus = get_selected_campus(request)
            if (
                cached["campus_mode"] != "existing"
                or campus is None
                or cached["campus_id"] != campus.pk
            ):
                messages.error(request, "La sede seleccionada cambió. Revisa el archivo otra vez.")
                return redirect("desktop-import")
            student_rows, enrollment_rows = review_package(package, campus)
            course_rows, _ = review_courses(package, campus)
            self.enforce_change_permissions(
                request, student_rows, enrollment_rows, course_rows, package
            )
        except OfflinePackageError as exc:
            messages.error(request, str(exc))
            return redirect("desktop-import")

        resolutions = self.posted_resolutions(request)
        unresolved = [
            row
            for row in student_rows + enrollment_rows
            if row["state"] == "conflict" and row["resolvable"]
        ]
        missing = [row for row in unresolved if row["source_id"] not in resolutions[row["kind"]]]
        if missing:
            for row in student_rows + enrollment_rows:
                row["selected_resolution"] = resolutions[row["kind"]].get(row["source_id"], "")
            messages.error(
                request, "Elige para cada conflicto si conservar la web o aplicar Desktop."
            )
            return self.render_preview(
                request, package, student_rows, enrollment_rows, token, course_rows
            )

        flat_resolutions = {
            f"{kind}:{source_id}": resolution
            for kind, choices in resolutions.items()
            for source_id, resolution in choices.items()
        }
        try:
            student_rows, enrollment_rows = review_package(package, campus, flat_resolutions)
            course_rows, _ = review_courses(package, campus)
            self.enforce_change_permissions(
                request, student_rows, enrollment_rows, course_rows, package
            )
            if any(row["state"] == "conflict" for row in student_rows + enrollment_rows):
                raise OfflinePackageError(
                    "Hay conflictos sin resolver; vuelve a revisar el paquete."
                )
            (
                created_courses,
                created_students,
                updated_students,
                created_enrollments,
                updated_enrollments,
            ) = import_package(
                package,
                campus,
                request,
                flat_resolutions,
                {
                    "student": request.user.has_perm("students.change_student"),
                    "enrollment": request.user.has_perm("students.change_enrollment"),
                    "course": request.user.has_perm("students.add_course"),
                },
            )
        except OfflinePackageError as exc:
            cache.delete(self.cache_key(request, token))
            request.session.pop(SESSION_TOKEN_KEY, None)
            messages.error(request, str(exc))
            return redirect("desktop-import")

        cache.delete(self.cache_key(request, token))
        request.session.pop(SESSION_TOKEN_KEY, None)
        return self.render_result(
            package,
            student_rows,
            enrollment_rows,
            (
                created_students,
                updated_students,
                created_enrollments,
                updated_enrollments,
            ),
            campus,
            course_rows=course_rows,
            created_courses=created_courses,
        )

    def render_preview(
        self, request, package, student_rows, enrollment_rows, token, course_rows=()
    ):
        if package["campus_mode"] == "new":
            return self.render_to_response(
                self.get_context_data(
                    initial_preview={
                        "bundle_id": package["bundle_id"],
                        "campus_name": package["campus_name"],
                        "campus_address": package["campus_address"],
                        "courses": package["courses"],
                        "promoters": package["promoters"],
                        "students": student_rows,
                        "enrollments": enrollment_rows,
                    },
                    import_token=token,
                )
            )
        can_import = any(
            row["state"] in ("new", "update") or (row["state"] == "conflict" and row["resolvable"])
            for row in course_rows + student_rows + enrollment_rows
        )
        return self.render_to_response(
            self.get_context_data(
                preview={
                    "bundle_id": package["bundle_id"],
                    "campus_name": package["campus_name"],
                    "courses": course_rows,
                    "students": student_rows,
                    "enrollments": enrollment_rows,
                    "can_import": can_import,
                    "preview_sections": (
                        ("Cursos", course_rows),
                        ("Estudiantes", student_rows),
                        ("Matrículas", enrollment_rows),
                    ),
                },
                import_token=token,
            )
        )

    @staticmethod
    def initial_rows(package):
        students = [
            {
                "kind": "student",
                "source_id": item["id"],
                "server_id": None,
                "label": f"{item['last_name']} {item['first_name']}".strip(),
                "state": "new",
                "message": "Se creará en la sede nueva.",
                "resolvable": False,
            }
            for item in package["students"]
        ]
        student_names = {
            item["id"]: f"{item['last_name']} {item['first_name']}".strip()
            for item in package["students"]
        }
        enrollments = [
            {
                "kind": "enrollment",
                "source_id": item["id"],
                "server_id": None,
                "label": student_names.get(item["student_id"], "Matrícula sin estudiante"),
                "state": "new",
                "message": "Se creará en la sede nueva.",
                "resolvable": False,
            }
            for item in package["enrollments"]
        ]
        return students, enrollments

    def render_result(
        self,
        package,
        student_rows,
        enrollment_rows,
        counts,
        campus,
        initial=False,
        course_rows=(),
        created_courses=None,
    ):
        created_students, updated_students, created_enrollments, updated_enrollments = counts
        result_sections = [
            ("Estudiantes", student_rows),
            ("Matrículas", enrollment_rows),
        ]
        if initial:
            result_sections[:0] = [
                (
                    "Cursos",
                    [
                        {
                            "kind": "course",
                            "label": item["name"],
                            "state": "Creado",
                            "message": f"{item['schedule']} · Grupo {item['group']}",
                        }
                        for item in package["courses"]
                    ],
                ),
                (
                    "Promotores",
                    [
                        {
                            "kind": "promoter",
                            "label": item["name"],
                            "state": "Vinculado",
                            "message": "Disponible en la sede.",
                        }
                        for item in package["promoters"]
                    ],
                ),
            ]
        elif course_rows:
            result_sections.insert(0, ("Cursos", course_rows))
        if created_courses is None:
            created_courses = (
                len(package["courses"])
                if initial
                else sum(row["state"] == "new" for row in course_rows)
            )
        return self.render_to_response(
            self.get_context_data(
                result={
                    "initial_campus": initial,
                    "campus_id": campus.pk,
                    "campus_name": campus.name,
                    "bundle_id": package["bundle_id"],
                    "created_courses": created_courses,
                    "linked_promoters": len(package["promoters"]) if initial else 0,
                    "created_students": created_students,
                    "updated_students": updated_students,
                    "created_enrollments": created_enrollments,
                    "updated_enrollments": updated_enrollments,
                    "skipped_students": sum(
                        row["state"] in ("error", "conflict") for row in student_rows
                    ),
                    "skipped_enrollments": sum(
                        row["state"] in ("error", "conflict", "omitted") for row in enrollment_rows
                    ),
                    "skipped_courses": sum(row["state"] == "error" for row in course_rows),
                    "students": student_rows,
                    "enrollments": enrollment_rows,
                    "result_sections": result_sections,
                }
            )
        )

    @staticmethod
    def posted_resolutions(request):
        choices = {"student": {}, "enrollment": {}}
        for key, value in request.POST.items():
            if not key.startswith("resolution:"):
                continue
            try:
                _, kind, source_id = key.split(":", 2)
            except ValueError:
                continue
            if kind in choices and value in ("web", "desktop"):
                choices[kind][source_id] = value
        return choices

    @staticmethod
    def enforce_change_permissions(
        request, student_rows, enrollment_rows, course_rows=(), package=None
    ):
        for rows, permission in (
            (student_rows, "students.change_student"),
            (enrollment_rows, "students.change_enrollment"),
        ):
            if request.user.has_perm(permission):
                continue
            for row in rows:
                if row["state"] in ("update", "conflict"):
                    row["state"] = "error"
                    row["resolvable"] = False
                    row["message"] = "No tienes permiso para modificar este registro."
        if request.user.has_perm("students.add_course"):
            return
        blocked_course_ids = set()
        for row in course_rows:
            if row["state"] == "new":
                row["state"] = "error"
                row["message"] = "No tienes permiso para crear cursos."
                blocked_course_ids.add(row["source_id"])
        if package is None:
            return
        for enrollment in package["enrollments"]:
            if enrollment["course_id"] not in blocked_course_ids:
                continue
            row = next(item for item in enrollment_rows if item["source_id"] == enrollment["id"])
            if row["state"] in ("new", "update"):
                row["state"] = "error"
                row["message"] = "No tienes permiso para crear el curso vinculado."

    @staticmethod
    def cache_key(request, token):
        return f"{CACHE_KEY_PREFIX}:{request.user.pk}:{token}"
