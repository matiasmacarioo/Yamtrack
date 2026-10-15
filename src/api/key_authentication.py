"""Static API key authentication for the REST API."""

from rest_framework.authentication import BaseAuthentication, get_authorization_header

from users.models import User

# "Authorization: Bearer <key>" splits into exactly two parts.
_BEARER_PARTS = 2


class ApiKeyAuthentication(BaseAuthentication):
    """Authenticate a request with a user's static API key.

    Accepts the key via ``Authorization: Bearer <key>`` or the ``X-API-Key``
    header. The key is the per-user ``User.token`` already used for external
    webhooks, so the same secret authorizes both the REST API and the MCP
    server (which sends it as a Bearer token).

    Returns ``None`` when no key is present or it is invalid, letting the other
    authenticators (JWT, session) try instead.
    """

    def authenticate_header(self, _request):
        """Advertise Bearer auth so 401 responses include WWW-Authenticate."""
        return "Bearer"

    def authenticate(self, request):
        """Resolve the user from the API key, or defer to other backends."""
        auth = get_authorization_header(request).split()
        if len(auth) == _BEARER_PARTS and auth[0].lower() == b"bearer":
            key = auth[1].decode()
        else:
            key = request.headers.get("x-api-key")
        if not key:
            return None

        try:
            user = User.objects.get(token=key)
        except User.DoesNotExist:
            return None
        if not user.is_active:
            return None
        return (user, key)
