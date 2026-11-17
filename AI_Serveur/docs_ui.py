"""The documentation page, served from this server's own files.

Swagger UI is vendored in `static/swagger-ui` (see its README) instead of loaded from a
CDN, so that opening the page contacts no other host.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api_docs import API_TITLE

ASSETS_DIR = Path(__file__).resolve().parent / "static" / "swagger-ui"
ASSETS_URL = "/docs/assets"

DOCS_PAGE = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{API_TITLE} - documentation</title>
<link rel="icon" type="image/png" href="{ASSETS_URL}/favicon.png">
<link rel="stylesheet" href="{ASSETS_URL}/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="{ASSETS_URL}/swagger-ui-bundle.js"></script>
<script src="{ASSETS_URL}/init.js"></script>
</body>
</html>
"""


def install_docs(app: FastAPI) -> None:
    @app.get("/docs", include_in_schema=False)
    async def docs() -> HTMLResponse:
        return HTMLResponse(DOCS_PAGE)

    app.mount(ASSETS_URL, StaticFiles(directory=ASSETS_DIR), name="docs-assets")
