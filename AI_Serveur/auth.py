import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

security = HTTPBearer(auto_error=False)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    if not settings.sso_salt_documents:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSO token verification is not configured",
        )

    # Replay decision: there is deliberately no `jti` store. A token lives 30 s, travels
    # over TLS, and the per-user quota is keyed on `sub`, so replaying a captured token
    # never gives anyone more budget than its owner already has. `jti` is still required
    # so every token stays unique and a store can be added later without reissuing tokens.
    try:
        return jwt.decode(
            credentials.credentials,
            settings.sso_salt_documents,
            algorithms=["HS256"],
            audience="documents",
            options={"require": ["exp", "sub", "jti"], "verify_sub": False},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
