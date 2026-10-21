from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core.campus import available_campuses

from .realtime import campus_group


class CallQueueConsumer(AsyncJsonWebsocketConsumer):
    """Mantiene abierta la página de la cola y le avisa cuando el equipo hace cambios."""

    group = None

    async def connect(self):
        self.group = await self.get_group()
        if self.group is None:
            await self.close()
            return
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def get_group(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_active:
            return None
        if not user.has_perm("calls.add_callnote"):
            return None
        session = self.scope.get("session")
        campus_id = session.get("selected_campus_id") if session is not None else None
        if not campus_id or not available_campuses(user).filter(pk=campus_id).exists():
            return None
        return campus_group(campus_id)

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content == {"type": "ping"}:
            await self.send_json({"type": "pong"})

    async def queue_changed(self, event):
        await self.send_json({"type": "changed"})
