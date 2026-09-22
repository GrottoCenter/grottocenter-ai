import httpx

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
    token = credentials.credentials
    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.auth_verify_url,
            headers={
                "Authorization": f"Bearer {token}",
            },
            timeout=10.0,
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        response_data = response.json()
        if response_data.get("success") is not True:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    return