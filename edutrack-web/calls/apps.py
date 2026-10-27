from django.apps import AppConfig


class CallsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "calls"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import CallClaim, CallNote, WhatsAppSend
        from .signals import queue_record_changed

        for model in (CallClaim, CallNote, WhatsAppSend):
            for signal in (post_save, post_delete):
                signal.connect(
                    queue_record_changed,
                    sender=model,
                    dispatch_uid=f"calls_queue_changed_{signal is post_save}_{model.__name__}",
                )
