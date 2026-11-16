from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from client.GreenPT import GreenPTClient
from config.settings import settings


@asynccontextmanager
async def httpClient(app: FastAPI, config=settings):
    if not config.api_key:
        raise RuntimeError(
            "GREENPT_API_KEY is required. Set it in the environment or in .env."
        )

    http_client = httpx.AsyncClient(
        base_url=config.greenpt_api_url,
        headers={
            "Authorization": f"Bearer {config.api_key}",
        },
        timeout=120.0,
    )

    app.state.greenpt_client = GreenPTClient(config.greenpt_api_url, config.api_key, http_client=http_client)

    yield

    await http_client.aclose()
