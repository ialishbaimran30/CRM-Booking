"""JWT authentication for WebSocket connections.

M-3 fix: browsers can't attach an Authorization header to a WebSocket
handshake, so the access token used to travel as a `?token=` query
parameter — which meant it ended up in reverse-proxy/CDN access logs and
browser history as a live, replayable bearer credential. It now travels as
a WebSocket subprotocol instead (`new WebSocket(url, ["jwt", token])`),
which is not part of the request line or query string that gets logged.
"""
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
    """Resolves scope["user"] from the Sec-WebSocket-Protocol header —
    ASGI exposes it as scope["subprotocols"], a list parsed from that
    header — expecting exactly ["jwt", "<access_token>"], using the
    project's existing SimpleJWT access tokens (the same auth mechanism
    already used for every REST API request)."""

    async def __call__(self, scope, receive, send):
        subprotocols = scope.get("subprotocols") or []
        token = subprotocols[1] if len(subprotocols) >= 2 and subprotocols[0] == "jwt" else None
        scope["user"] = await _get_user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)
