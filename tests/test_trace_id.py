"""Every request has a trace id: on the response, and on every log line written while it is handled."""

import asyncio
import io
import json
import logging
import re

import pytest

from tests.limits_support import (
    CHAT_URL,
    FRONT_ORIGIN,
    analyze,
    chat_reply,
    distinct_pdf,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tracing import JsonFormatter

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TRACE_A = "0198f3c2-7b1e-7c3a-9d4e-5f6a7b8c9d0e"
TRACE_B = "0198f3c2-7b1e-7c3a-9d4e-aaaaaaaaaaaa"


async def test_every_response_carries_a_generated_trace_id_when_the_caller_sent_none(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app() as (_app, client):
        ok = await analyze(client, distinct_pdf(1))
        unauthorized = await client.post(
            "/documents/analyze", files={"file": ("a.pdf", b"x", "application/pdf")}
        )
        missing = await client.get("/nothing-here")
        health = await client.get("/health")

    ids = [r.headers["x-trace-id"] for r in (ok, unauthorized, missing, health)]
    assert [r.status_code for r in (ok, unauthorized, missing, health)] == [200, 401, 404, 200]
    assert all(UUID_PATTERN.match(value) for value in ids)
    assert len(set(ids)) == 4


async def test_a_valid_trace_id_from_the_caller_is_kept_in_lower_case():
    async with running_app() as (_app, client):
        response = await client.get("/health", headers={"X-Trace-Id": TRACE_A.upper()})

    assert response.headers["x-trace-id"] == TRACE_A


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        TRACE_A + "0",
        TRACE_A[:-1],
        "x" * 500,
        '0198f3c2-7b1e-7c3a-9d4e-5f6a7b8c9d0e", "level": "CRITICAL',
        " " + TRACE_A,
        "",
    ],
)
async def test_a_trace_id_that_is_not_a_uuid_is_replaced_and_never_echoed(value):
    async with running_app() as (_app, client):
        response = await client.get("/health", headers={"X-Trace-Id": value})

    echoed = response.headers["x-trace-id"]
    assert UUID_PATTERN.match(echoed)
    assert echoed != value


async def test_refusals_sent_before_the_application_runs_carry_the_trace_id():
    async with running_app() as (_app, client):
        unauthorized = await client.post(
            "/documents/analyze",
            files={"file": ("a.pdf", b"x", "application/pdf")},
            headers={"X-Trace-Id": TRACE_A},
        )

    assert unauthorized.status_code == 401
    assert unauthorized.headers["x-trace-id"] == TRACE_A


async def test_log_lines_of_a_request_carry_its_trace_id(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1), user=42, **{"X-Trace-Id": TRACE_A})

    assert response.status_code == 200
    analysis = [line for line in log_lines() if "caller=42" in line["message"]]
    assert analysis, "the analysis wrote no log line"
    assert {line["trace_id"] for line in analysis} == {TRACE_A}


async def test_concurrent_requests_keep_their_own_trace_id_in_their_log_lines(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(json=chat_reply())
    async with running_app() as (_app, client):
        first, second = await asyncio.gather(
            analyze(client, distinct_pdf(1), user=41, **{"X-Trace-Id": TRACE_A}),
            analyze(client, distinct_pdf(2), user=43, **{"X-Trace-Id": TRACE_B}),
        )

    assert (first.status_code, second.status_code) == (200, 200)
    by_caller = {}
    for line in log_lines():
        for caller, expected in (("caller=41", TRACE_A), ("caller=43", TRACE_B)):
            if caller in line["message"]:
                by_caller.setdefault(caller, set()).add(line["trace_id"])
    assert by_caller == {"caller=41": {TRACE_A}, "caller=43": {TRACE_B}}


async def test_one_request_line_per_request_with_status_path_and_duration(respx_mock, log_lines):
    respx_mock.post(CHAT_URL).respond(500, text="down")
    async with running_app() as (_app, client):
        response = await analyze(
            client, distinct_pdf(1), **{"X-Trace-Id": TRACE_A}
        )

    requests = [line for line in log_lines() if line["logger"] == "request"]
    assert response.status_code == 502
    assert len(requests) == 1
    line = requests[0]
    assert line["trace_id"] == TRACE_A
    assert (line["http_method"], line["http_path"], line["http_status"]) == (
        "POST",
        "/documents/analyze",
        502,
    )
    assert isinstance(line["duration_ms"], int) and line["duration_ms"] >= 0


async def test_request_line_leaves_out_the_query_string_and_the_credentials(log_lines):
    async with running_app() as (_app, client):
        await client.get(
            "/nothing-here?secret=hunter2",
            headers={"Authorization": "Bearer abc.def.ghi", "X-Trace-Id": TRACE_A},
        )

    # The test client logs the URL it calls, query string included; only the server's own lines count.
    server_lines = [line for line in log_lines() if not line["logger"].startswith("httpx")]
    text = json.dumps(server_lines)
    assert "hunter2" not in text and "abc.def.ghi" not in text
    assert [line["http_path"] for line in server_lines if line["logger"] == "request"] == ["/nothing-here"]


async def test_health_probes_do_not_fill_the_log_at_info(log_lines):
    async with running_app() as (_app, client):
        await client.get("/health")
        await client.get("/ready")

    assert [line for line in log_lines() if line["logger"] == "request"] == []


def test_a_log_line_is_one_json_line_even_with_a_traceback_and_a_newline_in_the_message():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("format-test")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        try:
            raise RuntimeError("boom\nsecond line")
        except RuntimeError:
            logger.exception("failed\nline two")
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert output.count("\n") == 1
    line = json.loads(output)
    assert line["message"] == "failed\nline two"
    assert line["level"] == "ERROR"
    assert "RuntimeError: boom" in line["exception"]
    assert set(line) >= {"timestamp", "level", "logger", "message", "trace_id"}


def test_a_log_line_outside_a_request_has_no_trace_id_value():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)

    assert json.loads(JsonFormatter().format(record))["trace_id"] is None


async def test_preflight_allows_the_trace_id_header_and_responses_expose_it():
    async with running_app() as (_app, client):
        preflight = await client.options(
            "/documents/analyze",
            headers={
                "Origin": FRONT_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,x-trace-id",
            },
        )
        actual = await client.get("/health", headers={"Origin": FRONT_ORIGIN})

    assert preflight.status_code == 200
    assert "x-trace-id" in preflight.headers["access-control-allow-headers"].lower()
    exposed = actual.headers["access-control-expose-headers"].lower()
    assert "x-trace-id" in exposed and "retry-after" in exposed


async def test_every_documented_response_declares_the_trace_id_header():
    async with running_app() as (_app, client):
        document = (await client.get("/openapi.json")).json()

    responses = document["paths"]["/documents/analyze"]["post"]["responses"]
    assert [code for code, r in responses.items() if "X-Trace-Id" not in r.get("headers", {})] == []


@pytest.mark.parametrize(
    "path, pattern",
    [
        ("AI_Serveur/Dockerfile", r"^CMD \[(\"uvicorn\".*)\]"),
        ("docker-compose.dev.yml", r"command: \[(\"uvicorn\".*)\]"),
    ],
)
def test_uvicorn_does_not_write_its_own_access_log_which_has_no_trace_id(path, pattern):
    from pathlib import Path

    from tests.test_no_framework_fingerprint import ROOT, command_of

    assert "--no-access-log" in command_of(Path(ROOT) / path, pattern)


async def test_last_resort_500_outside_the_analysis_route_carries_the_trace_id_of_its_log_line(log_lines):
    import httpx

    from application import create_app
    from tests.limits_support import SharedMongo, make_limits_config

    app = create_app(make_limits_config(), SharedMongo())

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom detail")

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            sent = await client.get("/boom", headers={"X-Trace-Id": TRACE_A})
            generated = await client.get("/boom")

    assert (sent.status_code, generated.status_code) == (500, 500)
    assert sent.headers["x-trace-id"] == TRACE_A
    assert UUID_PATTERN.match(generated.headers["x-trace-id"])
    failures = [line for line in log_lines() if line["logger"] == "errors" and line["level"] == "ERROR"]
    assert {line["trace_id"] for line in failures} == {TRACE_A, generated.headers["x-trace-id"]}
