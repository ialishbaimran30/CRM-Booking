import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    """One personal group per user (`user_<id>`). notifications/services.py
    (CommunicationService._broadcast) sends into this group every time it
    creates a Notification row — this consumer only relays that same event
    down the socket, it never creates notifications itself."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        self.group_name = f"user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_message(self, event):
        """Handler for {"type": "notification.message", ...} group_send
        payloads (Channels maps the dotted type to this underscored method)."""
        await self.send(text_data=json.dumps({"notification": event["notification"]}))
