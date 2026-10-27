from .realtime import notify_queue_changed


def queue_record_changed(sender, instance, **kwargs):
    """Notas, reservas y marcas de WhatsApp cambian la tabla de la cola de su sede."""
    notify_queue_changed(instance.campus_id)
