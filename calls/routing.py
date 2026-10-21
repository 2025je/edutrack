from django.urls import path

from .consumers import CallQueueConsumer

websocket_urlpatterns = [
    path("ws/llamadas/cola/", CallQueueConsumer.as_asgi(), name="ws-calls-queue"),
]
