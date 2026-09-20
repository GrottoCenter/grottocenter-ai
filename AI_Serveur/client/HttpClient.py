from contextlib import asynccontextmanager

from client.GreenPT import GreenPTClient
from config.settings import settings
import httpx
from fastapi import FastAPI


@asynccontextmanager
async def httpClient(app: FastAPI):
    if not settings.api_key:
        raise RuntimeError(
            "GREENPT_API_KEY is required. Set it in the environment or in .env."
        )

    http_client = httpx.AsyncClient(
        base_url=settings.greenpt_api_url,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
        },
        timeout=60.0,
    )

    app.state.greenpt_client = GreenPTClient(settings.greenpt_api_url, settings.api_key, http_client=http_client)

    yield

    await http_client.aclose()