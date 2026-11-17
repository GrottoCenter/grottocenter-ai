"""The OpenAPI document: public on purpose, complete, and without the application or framework name."""

import json
import re
from pathlib import Path

import httpx
import pytest

from service.documentLlmAnalyzeService import LLMAnalyzerService
from tests.limits_support import (
    CHAT_URL,
    analyze,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)

SOURCE = Path(__file__).resolve().parent.parent / "AI_Serveur"

# What a consumer must never read: the application's name and anything that names the
# framework or a library behind it.
FORBIDDEN = [
    "grottocenter ai tools",
    "ai tools",
    "outils ia",
    "fastapi",
    "starlette",
    "pydantic",
    "uvicorn",
    "tiangolo",
    "jsdelivr",
]

ANALYZE_STATUSES = {"200", "401", "413", "415", "422", "429", "500", "502", "503", "504"}


async def fetch_document() -> dict:
    async with running_app() as (_app, client):
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def operation(document: dict) -> dict:
    return document["paths"]["/documents/analyze"]["post"]


def resolve(document: dict, schema: dict) -> dict:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    name = ref.rsplit("/", 1)[-1]
    return document["components"]["schemas"][name]


def response_schema(document: dict, status: str) -> dict:
    content = operation(document)["responses"][status]["content"]["application/json"]
    return resolve(document, content["schema"])


async def test_document_is_valid_json_with_a_neutral_title_and_no_french_description():
    document = await fetch_document()

    assert document["info"]["title"] == "Document metadata API"
    assert "description" in document["info"]
    assert "metadata" in document["info"]["description"].lower()
    assert not re.search(r"\b(pour|les|des|outils)\b", document["info"]["description"].lower())


async def test_document_names_neither_the_application_nor_the_framework():
    text = json.dumps(await fetch_document()).lower()

    assert [word for word in FORBIDDEN if word in text] == []


async def test_only_the_analysis_endpoint_is_documented_but_the_probes_still_answer():
    async with running_app() as (_app, client):
        document = (await client.get("/openapi.json")).json()
        root = await client.get("/")
        health = await client.get("/health")
        ready = await client.get("/ready")

    assert list(document["paths"]) == ["/documents/analyze"]
    assert list(document["paths"]["/documents/analyze"]) == ["post"]
    assert (root.status_code, health.status_code, ready.status_code) == (200, 200, 200)


async def test_every_status_the_endpoint_returns_is_declared():
    document = await fetch_document()

    assert set(operation(document)["responses"]) == ANALYZE_STATUSES


@pytest.mark.parametrize("status", sorted(ANALYZE_STATUSES - {"200"}))
async def test_error_responses_share_the_detail_body_and_say_when_they_happen(status):
    document = await fetch_document()
    declared = operation(document)["responses"][status]

    schema = response_schema(document, status)
    assert declared["description"].strip() not in ("", "Error")
    assert schema["properties"].keys() == {"detail"}
    assert schema["properties"]["detail"]["type"] == "string"
    assert schema["required"] == ["detail"]
    assert declared["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}


@pytest.mark.parametrize("status", ["429", "503"])
async def test_responses_that_ask_to_wait_declare_retry_after(status):
    document = await fetch_document()

    header = operation(document)["responses"][status]["headers"]["Retry-After"]

    assert header["schema"]["type"] == "string"
    assert "seconds" in header["description"].lower()


async def test_success_response_has_a_real_schema_and_an_example():
    document = await fetch_document()
    declared = operation(document)["responses"]["200"]["content"]["application/json"]

    schema = resolve(document, declared["schema"])

    assert schema["properties"].keys() == {"message", "filename", "document_metadata"}
    assert schema["properties"]["document_metadata"]["type"] == "array"
    assert declared["example"]["message"] == "success"
    assert declared["example"]["document_metadata"][0]["grottocenter_type"] in (
        document["components"]["schemas"]["GrottocenterType"]["enum"]
    )


async def test_metadata_schema_lists_the_allowed_values_of_type_and_rights():
    document = await fetch_document()
    schemas = document["components"]["schemas"]

    assert "book" in schemas["GrottocenterType"]["enum"]
    assert "CC-BY-SA" in schemas["LicenseName"]["enum"]
    assert "publication_date" in schemas["DocumentMetadata"]["properties"]


async def test_authentication_and_the_upload_are_described():
    document = await fetch_document()
    scheme = document["components"]["securitySchemes"]["bearerAuth"]
    description = operation(document)["description"]

    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    assert "sso/auth-token" in scheme["description"]
    assert '"product": "documents"' in scheme["description"]
    assert "30 seconds" in scheme["description"]
    assert "multipart/form-data" in description
    assert "`file`" in description
    assert operation(document)["security"] == [{"bearerAuth": []}]


async def test_component_and_operation_names_are_not_generated_by_the_framework():
    document = await fetch_document()
    names = list(document["components"]["schemas"])

    assert [name for name in names if name.startswith("Body_") or "Validation" in name] == []
    assert "AnalyzeUpload" in names
    assert operation(document)["operationId"] == "analyzeDocument"


# --- documented is a superset of returned -------------------------------------------------


async def documented(status: int, *, retry_after: bool = False):
    document = await fetch_document()
    declared = operation(document)["responses"]
    assert str(status) in declared, f"{status} is returned but not documented"
    if retry_after:
        assert "Retry-After" in declared[str(status)]["headers"]
    return declared[str(status)]


def assert_error_body(response: httpx.Response) -> None:
    body = response.json()
    assert list(body) == ["detail"]
    assert isinstance(body["detail"], str) and body["detail"]


async def test_returned_200_matches_the_documented_schema(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    await documented(response.status_code)
    schema = response_schema(await fetch_document(), "200")
    assert response.status_code == 200
    assert set(response.json()) == set(schema["properties"])


async def test_returned_401_is_documented():
    async with running_app() as (_app, client):
        response = await client.post(
            "/documents/analyze", files={"file": ("a.pdf", b"x", "application/pdf")}
        )

    assert response.status_code == 401
    await documented(401)
    assert_error_body(response)


async def test_returned_413_is_documented():
    async with running_app(make_limits_config(max_file_size_mb=1)) as (_app, client):
        response = await analyze(client, b"0" * (3 * 1024 * 1024))

    assert response.status_code == 413
    await documented(413)
    assert_error_body(response)


async def test_returned_415_is_documented():
    async with running_app() as (_app, client):
        response = await analyze(client, b"This is not a PDF.\n")

    assert response.status_code == 415
    await documented(415)
    assert_error_body(response)


async def test_returned_422_is_documented():
    async with running_app() as (_app, client):
        response = await analyze(client, b"")

    assert response.status_code == 422
    await documented(422)
    assert_error_body(response)


async def test_returned_429_is_documented_with_retry_after(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app(make_limits_config(user_daily_limit=1)) as (_app, client):
        await analyze(client, distinct_pdf(1))
        response = await analyze(client, distinct_pdf(2))

    assert response.status_code == 429
    await documented(429, retry_after=True)
    assert "retry-after" in response.headers
    assert_error_body(response)


async def test_returned_503_is_documented_with_retry_after(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app(make_limits_config(global_daily_limit=1)) as (_app, client):
        await analyze(client, distinct_pdf(1))
        response = await analyze(client, distinct_pdf(2), user=43)

    assert response.status_code == 503
    await documented(503, retry_after=True)
    assert "retry-after" in response.headers
    assert_error_body(response)


async def test_returned_503_for_the_kill_switch_is_documented():
    async with running_app(make_limits_config(analyze_enabled=False)) as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 503
    await documented(503)
    assert_error_body(response)


async def test_returned_502_is_documented(respx_mock):
    respx_mock.post(CHAT_URL).respond(500, text="down")
    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 502
    await documented(502)
    assert_error_body(response)


async def test_returned_504_is_documented(respx_mock):
    respx_mock.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("no answer"))
    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 504
    await documented(504)
    assert_error_body(response)


async def test_returned_500_is_documented(monkeypatch):
    async def broken(self, document_text):
        raise RuntimeError("boom")

    monkeypatch.setattr(LLMAnalyzerService, "analyze_document", broken)
    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 500
    await documented(500)
    assert_error_body(response)


def test_every_status_code_written_in_the_source_of_the_endpoint_is_documented():
    """A new `status_code=NNN` in the code of the endpoint fails here until it is documented."""
    files = [
        "service/documentService.py",
        "service/usageService.py",
        "errors.py",
        "auth.py",
        "middleware.py",
        "controller/documentController.py",
        "client/GreenPT.py",
    ]
    pattern = re.compile(r"status_code\s*=\s*(\d{3})|send_json_error\(send,\s*(\d{3})|HTTP_(\d{3})_")
    written = set()
    for name in files:
        path = SOURCE / name
        if not path.exists():
            continue
        for match in pattern.finditer(path.read_text()):
            written.add(next(group for group in match.groups() if group))

    # 404, 405 and the like are never produced by the endpoint itself. Upstream statuses that
    # the client reads (GreenPT's own) are never sent to the caller and are not in these files.
    undocumented = sorted(written - ANALYZE_STATUSES)

    assert undocumented == []

