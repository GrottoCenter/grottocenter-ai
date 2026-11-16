"""An upload without a valid token is refused before the server reads its body."""

import json
import time

import pytest

from auth import bearer_token
from config.settings import settings
from tests.limits_support import (
    CHAT_URL,
    FRONT_ORIGIN,
    SharedMongo,
    analyze,
    chat_reply,
    distinct_pdf,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tests.test_auth import MISSING, SECRET, forge_with_empty_key, mint

NOT_AUTHENTICATED = (401, "Invalid or missing token")
BAD_TOKEN = (401, "Invalid token")


async def post_raw(app, headers: dict[str, str], chunks=(b"x" * 64,)):
    """POST to the analysis endpoint through the ASGI interface, counting body reads.

    Returns the status, the JSON answer and how many times the application asked for
    the request body. Zero means the body was never read.
    """
    pending = list(chunks)
    reads = 0

    async def receive():
        nonlocal reads
        reads += 1
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        return {"type": "http.disconnect"}

    sent = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/documents/analyze",
        "raw_path": b"/documents/analyze",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=x"),
            *[(name.lower().encode(), value.encode()) for name, value in headers.items()],
        ],
        "client": ("203.0.113.9", 5000),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(body), reads


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


REJECTED = [
    pytest.param({}, NOT_AUTHENTICATED, id="no Authorization header"),
    pytest.param({"Authorization": "Basic dXNlcjpwYXNz"}, NOT_AUTHENTICATED, id="another auth scheme"),
    pytest.param({"Authorization": "Bearer"}, NOT_AUTHENTICATED, id="bearer scheme without a token"),
    pytest.param(bearer("not-a-jwt"), BAD_TOKEN, id="garbage token"),
    pytest.param(bearer(mint(exp=int(time.time()) - 5)), BAD_TOKEN, id="expired token"),
    pytest.param(bearer(mint(aud="superset")), BAD_TOKEN, id="token for another product"),
    pytest.param(bearer(mint(secret="another-secret-that-is-long-enough-123456")), BAD_TOKEN, id="wrong secret"),
    pytest.param(bearer(mint(secret=None, algorithm="none")), BAD_TOKEN, id="unsigned alg none"),
    pytest.param(bearer(mint(jti=MISSING)), BAD_TOKEN, id="token without jti"),
]


@pytest.mark.parametrize(("headers", "expected"), REJECTED)
async def test_upload_without_a_valid_token_gets_401_and_its_body_is_never_read(
    headers, expected, respx_mock
):
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())
    mongo = SharedMongo()

    async with running_app(mongo=mongo) as (app, _client):
        status, answer, reads = await post_raw(app, headers)

    assert (status, answer["detail"]) == expected
    assert reads == 0
    assert not chat.called
    assert mongo.database()["documents"].count_documents({}) == 0
    assert mongo.database()["usage"].count_documents({}) == 0


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(mint(), id="validly signed token"),
        pytest.param(forge_with_empty_key(), id="token forged with an empty key"),
    ],
)
async def test_unconfigured_secret_answers_503_and_reads_no_body(token, monkeypatch):
    monkeypatch.setattr(settings, "sso_salt_documents", "")

    async with running_app() as (app, _client):
        status, answer, reads = await post_raw(app, bearer(token))

    assert (status, answer["detail"]) == (503, "SSO token verification is not configured")
    assert reads == 0


async def test_oversized_upload_without_a_token_gets_401_not_413():
    async with running_app() as (app, _client):
        status, answer, reads = await post_raw(
            app, {"Content-Length": str(500 * 1024 * 1024)}
        )

    assert (status, answer["detail"]) == NOT_AUTHENTICATED
    assert reads == 0


async def test_oversized_upload_with_a_valid_token_gets_413():
    async with running_app() as (app, _client):
        status, answer, reads = await post_raw(
            app, {**bearer(mint()), "Content-Length": str(500 * 1024 * 1024)}
        )

    assert (status, answer["detail"]) == (413, "File too large: the limit is 50 MB")
    assert reads == 0


async def test_upload_with_a_valid_token_is_read_and_analysed(respx_mock):
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 200
    assert chat.call_count == 1


async def test_refusal_for_a_missing_token_carries_the_cors_headers_of_the_front():
    async with running_app() as (_app, client):
        response = await client.post(
            "/documents/analyze",
            files={"file": ("issue.pdf", distinct_pdf(1), "application/pdf")},
            headers={"Origin": FRONT_ORIGIN},
        )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN


async def test_preflight_from_the_front_needs_no_token():
    async with running_app() as (_app, client):
        response = await client.options(
            "/documents/analyze",
            headers={
                "Origin": FRONT_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN


async def test_other_routes_need_no_token():
    async with running_app() as (_app, client):
        health = await client.get("/health")
        ready = await client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code == 200


@pytest.mark.parametrize(
    ("header", "token"),
    [
        ("Bearer abc.def.ghi", "abc.def.ghi"),
        ("bearer abc.def.ghi", "abc.def.ghi"),
        ("BEARER abc.def.ghi", "abc.def.ghi"),
        ("Basic abc.def.ghi", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("", None),
        (None, None),
    ],
)
def test_bearer_token_is_read_the_way_the_security_scheme_reads_it(header, token):
    assert bearer_token(header) == token


def test_the_secret_used_by_these_tests_is_long_enough_for_hmac_sha256():
    # PyJWT warns about HMAC keys under 32 bytes, which would hide real warnings.
    assert len(SECRET.encode()) >= 32
