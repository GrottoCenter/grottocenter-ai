"""What the caller is told when GreenPT or the upload goes wrong."""

import logging

import httpx
import pytest

from application import create_app
from service.documentLlmAnalyzeService import LLMAnalyzerService
from tests.limits_support import (
    BASE_URL,
    CHAT_URL,
    FRONT_ORIGIN,
    OCR_URL,
    SharedMongo,
    analyze,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    mint,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)

UPSTREAM_SECRET = "UPSTREAM-INTERNAL-DETAIL-do-not-show"
FAILED = {"detail": "The analysis service failed. Try again later."}
TIMED_OUT = {"detail": "The analysis service did not answer in time. Try again later."}


async def post_empty(client):
    return await client.post(
        "/documents/analyze",
        files={"file": ("issue.pdf", b"", "application/pdf")},
        headers={"Authorization": f"Bearer {mint(sub=42)}"},
    )


# --- GreenPT chat -----------------------------------------------------------


@pytest.mark.parametrize("upstream_status", [400, 401, 403, 429, 500, 502, 503])
async def test_greenpt_chat_error_status_gives_502_and_shows_nothing_of_the_upstream_answer(
    upstream_status, respx_mock
):
    respx_mock.post(CHAT_URL).respond(upstream_status, text=UPSTREAM_SECRET)

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 502
    assert response.json() == FAILED
    assert UPSTREAM_SECRET not in response.text


async def test_greenpt_rejecting_this_servers_key_is_not_reported_as_a_bad_user_token(respx_mock):
    respx_mock.post(CHAT_URL).respond(401, json={"error": "invalid api key"})

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 502
    assert "WWW-Authenticate" not in response.headers


async def test_greenpt_chat_timeout_gives_504(respx_mock):
    respx_mock.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("no answer"))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 504
    assert response.json() == TIMED_OUT


async def test_greenpt_connection_failure_gives_502_not_504(respx_mock):
    respx_mock.post(CHAT_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 502
    assert response.json() == FAILED


async def test_greenpt_chat_answer_that_is_not_json_gives_502(respx_mock):
    respx_mock.post(CHAT_URL).respond(200, text=f"<html>{UPSTREAM_SECRET}</html>")

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 502
    assert UPSTREAM_SECRET not in response.text


async def test_failed_analysis_stores_nothing(respx_mock):
    respx_mock.post(CHAT_URL).respond(500, text="down")
    mongo = SharedMongo()

    async with running_app(mongo=mongo) as (_app, client):
        await analyze(client, distinct_pdf(1))

    assert mongo.database()["documents"].count_documents({}) == 0


# --- GreenPT OCR ------------------------------------------------------------


async def test_greenpt_ocr_error_gives_502_and_no_chat_call(respx_mock, short_text_pdf):
    ocr = respx_mock.post(OCR_URL).respond(500, text=UPSTREAM_SECRET)
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())

    async with running_app() as (_app, client):
        response = await analyze(client, short_text_pdf)

    assert ocr.call_count == 1
    assert not chat.called
    assert response.status_code == 502
    assert response.json() == FAILED
    assert UPSTREAM_SECRET not in response.text


async def test_greenpt_ocr_timeout_gives_504(respx_mock, short_text_pdf):
    respx_mock.post(OCR_URL).mock(side_effect=httpx.ConnectTimeout("slow"))

    async with running_app() as (_app, client):
        response = await analyze(client, short_text_pdf)

    assert response.status_code == 504
    assert response.json() == TIMED_OUT


# --- what is logged ---------------------------------------------------------


async def test_greenpt_failure_is_logged_with_its_status_and_body_but_not_shown(
    respx_mock, caplog
):
    respx_mock.post(CHAT_URL).respond(503, text=UPSTREAM_SECRET)

    with caplog.at_level(logging.ERROR, logger="client.GreenPT"):
        async with running_app() as (_app, client):
            response = await analyze(client, distinct_pdf(1))

    logged = [r.getMessage() for r in caplog.records if r.name == "client.GreenPT"]
    assert len(logged) == 1
    assert "chat failed" in logged[0]
    assert "status=503" in logged[0]
    assert UPSTREAM_SECRET in logged[0]
    assert UPSTREAM_SECRET not in response.text


async def test_logged_greenpt_body_is_cut_to_500_characters(respx_mock, caplog):
    respx_mock.post(CHAT_URL).respond(500, text="x" * 5000)

    with caplog.at_level(logging.ERROR, logger="client.GreenPT"):
        async with running_app() as (_app, client):
            await analyze(client, distinct_pdf(1))

    message = next(r.getMessage() for r in caplog.records if r.name == "client.GreenPT")
    assert message.count("x") == 500


async def test_greenpt_timeout_is_logged(respx_mock, caplog):
    respx_mock.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("no answer"))

    with caplog.at_level(logging.ERROR, logger="client.GreenPT"):
        async with running_app() as (_app, client):
            await analyze(client, distinct_pdf(1))

    assert any("chat timed out" in r.getMessage() for r in caplog.records)


# --- input that cannot be analysed ------------------------------------------


async def test_empty_upload_gives_422(respx_mock):
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())

    async with running_app() as (_app, client):
        response = await post_empty(client)

    assert response.status_code == 422
    assert response.json() == {"detail": "Uploaded file is empty"}
    assert not chat.called


async def test_pdf_without_text_and_with_empty_ocr_gives_422_and_stores_nothing(
    respx_mock, blank_pdf
):
    respx_mock.post(OCR_URL).respond(json="")
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())
    mongo = SharedMongo()

    async with running_app(mongo=mongo) as (_app, client):
        response = await analyze(client, blank_pdf)

    assert response.status_code == 422
    assert response.json() == {"detail": "No text could be extracted from the PDF"}
    assert not chat.called
    assert mongo.database()["documents"].count_documents({}) == 0


# --- unexpected errors ------------------------------------------------------


async def test_unexpected_error_in_the_analysis_gives_a_generic_500_and_logs_the_traceback(
    respx_mock, monkeypatch, caplog
):
    async def broken(self, document_text):
        raise RuntimeError("internal detail /srv/app/secret_path.py")

    monkeypatch.setattr(LLMAnalyzerService, "analyze_document", broken)

    with caplog.at_level(logging.ERROR, logger="controller.documentController"):
        async with running_app() as (_app, client):
            response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "internal detail" not in response.text
    assert "Traceback" not in response.text
    record = next(r for r in caplog.records if r.name == "controller.documentController")
    assert record.exc_info is not None
    assert "internal detail /srv/app/secret_path.py" in str(record.exc_info[1])


async def test_unexpected_error_still_carries_the_cors_headers_the_front_needs(monkeypatch):
    async def broken(self, document_text):
        raise RuntimeError("boom")

    monkeypatch.setattr(LLMAnalyzerService, "analyze_document", broken)

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1), Origin=FRONT_ORIGIN)

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN


async def test_error_outside_the_analysis_route_gives_a_generic_500_json_and_is_logged(caplog):
    app = create_app(make_limits_config(), SharedMongo())

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom detail")

    with caplog.at_level(logging.ERROR, logger="errors"):
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
                response = await client.get("http://testserver/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "kaboom" not in response.text
    record = next(r for r in caplog.records if r.name == "errors")
    assert str(record.exc_info[1]) == "kaboom detail"
