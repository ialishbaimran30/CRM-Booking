from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from bookings.asgi import application


class NotificationSocketAuthTests(TestCase):
    """M-3: the JWT travels as a WebSocket subprotocol (["jwt", token]),
    not a URL query string — confirms the full middleware+consumer path,
    not just the middleware in isolation."""

    @staticmethod
    def _make_user_and_token():
        # RefreshToken.for_user() writes an OutstandingToken row (the
        # token_blacklist app tracks every issued token), so this whole
        # step — not just user creation — must run off the async event
        # loop via database_sync_to_async, or Django raises
        # SynchronousOnlyOperation.
        user = User.objects.create_user(
            username="wsuser", email="wsuser@example.com", password="test-pass-12345"
        )
        return str(RefreshToken.for_user(user).access_token)

    async def _get_token(self):
        return await database_sync_to_async(self._make_user_and_token)()

    async def test_valid_token_via_subprotocol_is_accepted(self):
        token = await self._get_token()

        communicator = WebsocketCommunicator(application, "/ws/notifications/", subprotocols=["jwt", token])
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        self.assertEqual(subprotocol, "jwt")
        await communicator.disconnect()

    async def test_missing_subprotocol_is_rejected(self):
        communicator = WebsocketCommunicator(application, "/ws/notifications/")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_token_in_query_string_no_longer_authenticates(self):
        # The old M-3 transport must no longer work now that the middleware
        # only reads scope["subprotocols"].
        token = await self._get_token()
        communicator = WebsocketCommunicator(application, f"/ws/notifications/?token={token}")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_invalid_token_is_rejected(self):
        communicator = WebsocketCommunicator(
            application, "/ws/notifications/", subprotocols=["jwt", "not-a-real-token"]
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
