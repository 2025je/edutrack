"""Avisos en vivo de la cola de llamadas por WebSocket (Django Channels).

Solo se avisa que «algo cambió» en la sede; cada navegador vuelve a pedir su estado
a `calls-queue-status`, que ya aplica permisos y calcula los datos de cada usuario.
"""

import logging
from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

logger = logging.getLogger(__name__)

QUEUE_CHANGED = "queue.changed"


def campus_group(campus_id):
    return f"calls.campus.{campus_id}"


def broadcast(campus_id):
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(campus_group(campus_id), {"type": QUEUE_CHANGED})
    except Exception:
        # Un fallo de Redis no debe romper la operación: los navegadores siguen consultando.
        logger.warning("No se pudo avisar el cambio de la cola de llamadas", exc_info=True)


def notify_queue_changed(campus_id):
    """Avisa al equipo de la sede cuando la transacción actual se confirme."""
    if campus_id:
        transaction.on_commit(partial(broadcast, campus_id))
