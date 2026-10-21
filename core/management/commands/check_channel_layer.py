import asyncio
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Comprueba que la capa de canales puede enviar y recibir mensajes."

    def handle(self, *args, **options):
        layer = get_channel_layer()
        if layer is None:
            raise CommandError("No hay una capa de canales configurada.")
        try:
            async_to_sync(self._check_layer)(layer)
        except Exception as exc:
            raise CommandError(f"La capa de canales no está disponible: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("La capa de canales está disponible."))

    @staticmethod
    async def _check_layer(layer):
        channel = await layer.new_channel("healthcheck.")
        message = {"type": "health.check", "nonce": uuid.uuid4().hex}
        await layer.send(channel, message)
        received = await asyncio.wait_for(layer.receive(channel), timeout=5)
        if received != message:
            raise CommandError("La capa de canales devolvió un mensaje inesperado.")
