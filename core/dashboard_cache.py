"""Caché de las cifras del panel principal.

Las cifras se guardan por sede y día bajo un número de versión global. Cualquier cambio
en alumnos, matrículas, cursos, promotores, cuotas o pagos incrementa la versión, de modo
que el panel nunca muestra datos anteriores a una modificación. El TTL es solo un respaldo
para cambios que no emiten señales (por ejemplo, actualizaciones masivas con `update()`).
"""

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save

VERSION_KEY = "dashboard:version"
TTL_SECONDS = 300


def current_version():
    cache.add(VERSION_KEY, 1, None)
    return cache.get(VERSION_KEY, 1)


def bump_version():
    cache.add(VERSION_KEY, 1, None)
    try:
        cache.incr(VERSION_KEY)
    except ValueError:
        cache.set(VERSION_KEY, 2, None)


def cached_group(group, campus_id, today, compute):
    key = f"dashboard:{current_version()}:{group}:{campus_id}:{today.isoformat()}"
    value = cache.get(key)
    if value is None:
        value = compute()
        cache.set(key, value, TTL_SECONDS)
    return value


def _invalidate(**kwargs):
    # Se invalida ya y otra vez al confirmar la transacción, para que ninguna lectura
    # concurrente deje guardados datos anteriores al cambio.
    bump_version()
    transaction.on_commit(bump_version)


def connect_signals():
    from payments.models import Installment, Payment, PaymentAllocation
    from students.models import Course, Enrollment, Ficha, Promoter, Student

    for model in (
        Student,
        Enrollment,
        Ficha,
        Course,
        Promoter,
        Payment,
        PaymentAllocation,
        Installment,
    ):
        uid = f"dashboard-cache-{model.__name__}"
        post_save.connect(_invalidate, sender=model, dispatch_uid=f"{uid}-save")
        post_delete.connect(_invalidate, sender=model, dispatch_uid=f"{uid}-delete")
    m2m_changed.connect(
        _invalidate,
        sender=Promoter.campuses.through,
        dispatch_uid="dashboard-cache-promoter-campuses",
    )
