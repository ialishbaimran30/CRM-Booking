"""JWT authentication for WebSocket connections.

Browsers can't attach an Authorization header to a WebSocket handshake, so
the client passes the same JWT access token it already uses for REST calls
as a query parameter instead: ws://host/ws/notifications/?token=<access_token>
"""
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_user_from_token(token):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        validated = AccessToken(token)
        return User.objects.get(id=validated["user_id"])
    except (TokenError, InvalidToken, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Resolves scope["user"] from a `?token=` query param using the
    project's existing SimpleJWT access tokens — the same auth mechanism
    already used for every REST API request."""

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        token = parse_qs(query_string).get("token", [None])[0]
        scope["user"] = await _get_user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
