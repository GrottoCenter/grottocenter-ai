import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from auth import verify_token
from config.settings import settings

# 46 bytes: PyJWT warns about HMAC keys shorter than 32 bytes.
SECRET = "unit-test-sso-secret-that-is-long-enough-1234"
MISSING = object()


def mint(secret: str | None = SECRET, algorithm: str = "HS256", **overrides) -> str:
    """A token shaped like the ones grottocenter-api's SsoService issues for `documents`."""
    payload = {
        "sub": 42,
        "aud": "documents",
        "email": "42@grottocenter.org",
        "firstName": "Ada",
        "lastName": "Lovelace",
        "jti": "11111111-2222-3333-4444-555555555555",
        "exp": int(time.time()) + 30,
    }
    payload.update(overrides)
    payload = {key: value for key, value in payload.items() if value is not MISSING}
    return jwt.encode(payload, secret, algorithm=algorithm)


def forge_with_empty_key() -> str:
    """An HS256 token signed with an empty key, which PyJWT itself refuses to produce.

    This is what an attacker would send to a server whose secret is accidentally empty.
    """

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64(
        json.dumps(
            {"sub": 42, "aud": "documents", "jti": "x", "exp": int(time.time()) + 30}
        ).encode()
    )
    signature = hmac.new(b"", f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64(signature)}"


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "sso_salt_documents", SECRET)


async def test_valid_token_returns_its_claims_with_the_integer_subject():
    claims = await verify_token(bearer(mint()))

    assert claims["sub"] == 42
    assert claims["aud"] == "documents"
    assert claims["jti"] == "11111111-2222-3333-4444-555555555555"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(mint(exp=int(time.time()) - 5), id="expired"),
        pytest.param(mint(aud="superset"), id="audience of another product"),
        pytest.param(mint(aud=MISSING), id="no audience"),
        pytest.param(mint(secret="another-secret-of-more-than-32-bytes-xx"), id="wrong secret"),
        pytest.param(mint(secret=None, algorithm="none"), id="unsigned alg none"),
        pytest.param(mint(exp=MISSING), id="no exp"),
        pytest.param(mint(sub=MISSING), id="no sub"),
        pytest.param(mint(jti=MISSING), id="no jti"),
        pytest.param("not-a-jwt", id="not a jwt"),
    ],
)
async def test_invalid_token_is_rejected_with_401(token):
    with pytest.raises(HTTPException) as error:
        await verify_token(bearer(token))

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid token"


async def test_request_without_credentials_is_rejected_with_401():
    with pytest.raises(HTTPException) as error:
        await verify_token(None)

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid or missing token"


async def test_unconfigured_secret_answers_503_and_accepts_no_token(monkeypatch):
    monkeypatch.setattr(settings, "sso_salt_documents", "")

    with pytest.raises(HTTPException) as signed_with_a_real_secret:
        await verify_token(bearer(mint()))
    with pytest.raises(HTTPException) as signed_with_an_empty_key:
        await verify_token(bearer(forge_with_empty_key()))

    assert signed_with_a_real_secret.value.status_code == 503
    assert signed_with_an_empty_key.value.status_code == 503
