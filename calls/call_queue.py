"""Cola de llamadas: cada usuario pide un alumno de su sublista y el resto del equipo lo ve."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from students.models import Student

from .models import CallClaim, CallList, CallNote


def expire_stale(call_list):
    limit = timezone.now() - timedelta(minutes=CallClaim.MINUTES)
    return CallClaim.objects.filter(
        call_list=call_list, status=CallClaim.Status.ACTIVE, started_at__lt=limit
    ).update(status=CallClaim.Status.EXPIRED, finished_at=timezone.now())


def user_list(user):
    """Sublista activa del usuario, o None si no pertenece a ninguna."""
    return CallList.objects.filter(members__user=user, active=True).select_related("campus").first()


def active_claim(user, call_list):
    expire_stale(call_list)
    return (
        CallClaim.objects.filter(user=user, call_list=call_list, status=CallClaim.Status.ACTIVE)
        .select_related("student")
        .first()
    )


def team_claims(call_list, exclude_user=None):
    expire_stale(call_list)
    claims = CallClaim.objects.filter(
        call_list=call_list, status=CallClaim.Status.ACTIVE
    ).select_related("student", "user")
    return claims.exclude(user=exclude_user) if exclude_user else claims


def pending_students(call_list):
    """Alumnos de la sublista sin llamada hoy ni reclamados; primero los menos contactados."""
    today = timezone.localdate()
    taken = CallClaim.objects.filter(status=CallClaim.Status.ACTIVE).values("student")
    called_today = (
        CallNote.objects.filter(created_at__date=today)
        .exclude(response=CallNote.Response.NO_ANSWER)
        .exclude(response=CallNote.Response.WRONG_NUMBER)
        .values("student")
    )
    return (
        Student.objects.filter(
            active=True,
            campus=call_list.campus,
            enrollments__active=True,
            enrollments__call_lists=call_list,
        )
        .exclude(pk__in=taken)
        .exclude(pk__in=called_today)
        .exclude(phone="")
        .annotate(last_contact=Max("call_notes__created_at"))
        .distinct()
        .order_by(F("last_contact").asc(nulls_first=True), "full_name", "pk")
    )


def claim_next(user, call_list, student_id=None):
    """Reserva el siguiente alumno (o uno concreto de los pendientes); devuelve (reclamo, creado)."""
    try:
        with transaction.atomic():
            CallList.objects.select_for_update().get(pk=call_list.pk)
            current = active_claim(user, call_list)
            if current:
                return current, False
            pending = pending_students(call_list)
            student = pending.filter(pk=student_id).first() if student_id else pending.first()
            if student is None:
                return None, False
            claim = CallClaim.objects.create(
                campus=call_list.campus, call_list=call_list, student=student, user=user
            )
            return claim, True
    except IntegrityError:
        return None, False


def close_claim(user, student, status=CallClaim.Status.DONE):
    return CallClaim.objects.filter(
        user=user, student=student, status=CallClaim.Status.ACTIVE
    ).update(status=status, finished_at=timezone.now())
