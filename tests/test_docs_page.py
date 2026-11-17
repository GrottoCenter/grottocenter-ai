"""The documentation page: served by this server, with nothing fetched from another host."""

import re
from pathlib import Path

from tests.limits_support import running_app, sso_secret  # noqa: F401 - autouse fixture

ASSETS = Path(__file__).resolve().parent.parent / "AI_Serveur" / "static" / "swagger-ui"
NAMES = ["fastapi", "starlette", "pydantic", "uvicorn", "tiangolo", "jsdelivr", "grottocenter ai tools"]


async def fetch(path: str):
    async with running_app() as (_app, client):
        return await client.get(path)


async def test_docs_page_is_html_with_a_neutral_title():
    response = await fetch("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Document metadata API - documentation</title>" in response.text
    assert [name for name in NAMES if name in response.text.lower()] == []


async def test_docs_page_loads_only_from_this_server():
    html = (await fetch("/docs")).text

    references = re.findall(r'(?:src|href)="([^"]+)"', html)

    assert references, "the page loads nothing: it cannot render"
    assert [ref for ref in references if not ref.startswith("/docs/assets/")] == []


async def test_page_script_points_at_this_servers_document_and_turns_off_the_online_validator():
    script = (await fetch("/docs/assets/init.js")).text

    assert 'url: "/openapi.json"' in script
    assert "validatorUrl: null" in script
    assert "http://" not in script and "https://" not in script


async def test_assets_are_served():
    bundle = await fetch("/docs/assets/swagger-ui-bundle.js")
    css = await fetch("/docs/assets/swagger-ui.css")
    icon = await fetch("/docs/assets/favicon.png")

    assert bundle.status_code == css.status_code == icon.status_code == 200
    assert "javascript" in bundle.headers["content-type"]
    assert "SwaggerUIBundle" in bundle.text
    assert css.headers["content-type"].startswith("text/css")
    assert icon.content[:4] == b"\x89PNG"


async def test_redoc_and_the_stock_oauth_redirect_are_not_served():
    redoc = await fetch("/redoc")
    redirect = await fetch("/docs/oauth2-redirect")

    assert (redoc.status_code, redoc.json()) == (404, {"detail": "Not Found"})
    assert redirect.status_code == 404


async def test_a_missing_asset_is_a_404_with_the_usual_body():
    response = await fetch("/docs/assets/nothing.js")

    assert (response.status_code, response.json()) == (404, {"detail": "Not Found"})


def test_vendored_assets_carry_their_licence_and_do_not_name_the_framework():
    assert "Apache License" in (ASSETS / "LICENSE").read_text()
    assert (ASSETS / "NOTICE").exists()
    for name in ("swagger-ui-bundle.js", "swagger-ui.css"):
        text = (ASSETS / name).read_text(errors="ignore").lower()
        assert [word for word in ("fastapi", "tiangolo", "jsdelivr") if word in text] == []
