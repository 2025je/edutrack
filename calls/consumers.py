import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core.campus import available_campuses

from .call_queue import user_list
from .realtime import campus_group

logger = logging.getLogger(__name__)


class CallQueueConsumer(AsyncJsonWebsocketConsumer):
    """Mantiene abierta la página de la cola y le avisa cuando el equipo hace cambios."""

    group = None
    campus_id = None

    async def connect(self):
        self.campus_id = await self.get_authorized_campus_id()
        if self.campus_id is None:
            await self.close()
            return
        self.group = campus_group(self.campus_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        logger.info(
            "WebSocket de cola conectado: user_id=%s campus_id=%s",
            self.scope["user"].pk,
            self.campus_id,
        )

    @database_sync_to_async
    def get_authorized_campus_id(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_active:
            return None
        if not user.has_perm("calls.add_callnote"):
            return None
        session = self.scope.get("session")
        campus_id = session.get("selected_campus_id") if session is not None else None
        try:
            campus_id = int(campus_id)
        except (TypeError, ValueError):
            return None
        if not available_campuses(user).filter(pk=campus_id).exists():
            return None
        call_list = user_list(user)
        if call_list is None or call_list.campus_id != campus_id:
            return None
        return call_list.campus_id

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)
            logger.info(
                "WebSocket de cola desconectado: user_id=%s campus_id=%s code=%s",
                self.scope["user"].pk,
                self.campus_id,
                code,
            )

    async def receive_json(self, content, **kwargs):
        if content == {"type": "ping"}:
            if self.group:
                await self.channel_layer.group_add(self.group, self.channel_name)
            await self.send_json({"type": "pong"})

    async def queue_changed(self, event):
        await self.send_json({"type": "changed"})
