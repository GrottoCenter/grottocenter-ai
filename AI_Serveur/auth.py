import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api_docs import BEARER_DESCRIPTION, BEARER_SCHEME_NAME
from config.settings import settings

security = HTTPBearer(
    scheme_name=BEARER_SCHEME_NAME,
    description=BEARER_DESCRIPTION,
    bearerFormat="JWT",
    auto_error=False,
)


class AuthError(Exception):
    """A request that cannot be authenticated: 401 for a bad token, 503 if verification is not configured."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def bearer_token(authorization: str | None) -> str | None:
    """The token of an `Authorization: Bearer <token>` header, read the way HTTPBearer reads it."""
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if not scheme or not credentials or scheme.lower() != "bearer":
        return None
    return credentials


def authenticate(token: str | None) -> dict:
    """Verify an SSO token and return its claims, or raise AuthError.

    This is the one place that decides whether a token is good. It is used by the
    `verify_token` dependency and by the middleware that refuses an unauthenticated
    upload before its body is read, so the two cannot disagree.
    """
    if not token:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
    if not settings.sso_salt_documents:
        raise AuthError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SSO token verification is not configured",
        )

    # Replay decision: there is deliberately no `jti` store. A token lives 30 s, travels
    # over TLS, and the per-user quota is keyed on `sub`, so replaying a captured token
    # never gives anyone more budget than its owner already has. `jti` is still required
    # so every token stays unique and a store can be added later without reissuing tokens.
    try:
        return jwt.decode(
            token,
            settings.sso_salt_documents,
            algorithms=["HS256"],
            audience="documents",
            options={"require": ["exp", "sub", "jti"], "verify_sub": False},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return authenticate(credentials.credentials if credentials else None)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
