"""Browsers on a developer's machine and on staging deployments may call the server too."""

import subprocess
import sys
from pathlib import Path

import pytest

from config.settings import (
    LOCALHOST_ORIGIN_REGEX,
    build_origin_regex,
    parse_bool,
    validate_settings,
)
from tests.test_runtime_config import FRONT_ORIGIN, build_app, client_for, make_config

# Written with [0-9] and [.] so that no backslash has to survive a .env file or compose.
STAGING_REGEX = "https://orange-rock-0d4f87503-[0-9]+[.]westeurope[.]azurestaticapps[.]net"
APP_DIR = Path(__file__).resolve().parent.parent / "AI_Serveur"

ALLOWED_LOCAL = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "https://localhost:3443",
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://[::1]:8080",
    "http://localhost:65535",
]
REFUSED_LOCAL = [
    "http://localhost.evil.example",
    "http://localhost.evil.example:3000",
    "http://evil.example:3000",
    "http://notlocalhost:3000",
    "http://localhost:3000.evil.example",
    "http://localhost:999999",
    "http://localhost:",
    "http://localhost:abc",
    "http://127.0.0.1.evil.example",
    "http://127.0.0.2:3000",
    "ftp://localhost:3000",
    "http://user@localhost:3000",
    "http://localhost:3000/",
    "null",
]
ALLOWED_STAGING = [
    "https://orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503-1.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503-99999.westeurope.azurestaticapps.net",
]
REFUSED_STAGING = [
    "https://orange-rock-0d4f87503-.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503-12a.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503.westeurope.azurestaticapps.net",
    "http://orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net.evil.example",
    "https://evil-orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net",
    "https://orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net:8443",
    "https://orange-rock-0d4f87503-1636.eastus.azurestaticapps.net",
    "https://orange-rock-0d4f87503-1636.westeurope.azurestaticapps.net/",
    "https://orange-rock-9999999-1636.westeurope.azurestaticapps.net",
    "https://evil.example",
]


async def preflight(client, origin):
    return await client.options(
        "/documents/analyze",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )


async def assert_allowed(app, origins):
    async with client_for(app) as client:
        for origin in origins:
            response = await preflight(client, origin)
            assert response.status_code == 200, origin
            assert response.headers["access-control-allow-origin"] == origin, origin
            assert "access-control-allow-credentials" not in response.headers, origin


async def assert_refused(app, origins):
    async with client_for(app) as client:
        for origin in origins:
            response = await preflight(client, origin)
            assert response.status_code == 400, origin
            assert "access-control-allow-origin" not in response.headers, origin


# --- building the pattern the middleware uses ----------------------------------


def test_no_pattern_when_neither_localhost_nor_a_regex_is_configured():
    assert build_origin_regex(False, "") is None
    assert build_origin_regex(False, "   ") is None
    assert build_origin_regex(None, "") is None


def test_the_localhost_switch_and_the_regex_are_combined_as_alternatives():
    assert build_origin_regex(True, "") == f"(?:{LOCALHOST_ORIGIN_REGEX})"
    assert build_origin_regex(False, STAGING_REGEX) == f"(?:{STAGING_REGEX})"
    assert build_origin_regex(True, STAGING_REGEX) == f"(?:{LOCALHOST_ORIGIN_REGEX})|(?:{STAGING_REGEX})"


def test_a_regex_that_does_not_compile_is_ignored_so_the_validation_can_report_it():
    assert build_origin_regex(False, "https://[unclosed") is None
    assert build_origin_regex(True, "https://[unclosed") == f"(?:{LOCALHOST_ORIGIN_REGEX})"


# --- behaviour through the application -----------------------------------------


@pytest.mark.parametrize("origin", ALLOWED_LOCAL)
async def test_localhost_origins_are_allowed_when_the_switch_is_on(origin):
    await assert_allowed(build_app(cors_allow_localhost=True), [origin])


@pytest.mark.parametrize("origin", REFUSED_LOCAL)
async def test_lookalikes_of_localhost_are_refused_when_the_switch_is_on(origin):
    await assert_refused(build_app(cors_allow_localhost=True), [origin])


@pytest.mark.parametrize("origin", ALLOWED_LOCAL)
async def test_localhost_is_refused_by_default(origin):
    await assert_refused(build_app(), [origin])
    await assert_refused(build_app(cors_allow_localhost=False), [origin])


@pytest.mark.parametrize("origin", ALLOWED_STAGING)
async def test_every_numbered_staging_origin_is_allowed_with_the_regex(origin):
    await assert_allowed(build_app(cors_origin_regex=STAGING_REGEX), [origin])


@pytest.mark.parametrize("origin", REFUSED_STAGING)
async def test_lookalikes_of_the_staging_origin_are_refused(origin):
    await assert_refused(build_app(cors_origin_regex=STAGING_REGEX), [origin])


async def test_the_staging_regex_does_not_open_localhost_and_the_switch_does_not_open_staging():
    await assert_refused(build_app(cors_origin_regex=STAGING_REGEX), ["http://localhost:3000"])
    await assert_refused(build_app(cors_allow_localhost=True), ALLOWED_STAGING)


async def test_the_listed_origin_keeps_working_next_to_the_patterns():
    app = build_app(cors_allow_localhost=True, cors_origin_regex=STAGING_REGEX)

    await assert_allowed(app, [FRONT_ORIGIN, "http://localhost:3000", ALLOWED_STAGING[0]])
    await assert_refused(app, ["https://evil.example", "http://localhost.evil.example"])


async def test_an_actual_request_from_an_allowed_pattern_origin_gets_the_cors_header():
    app = build_app(cors_allow_localhost=True, cors_origin_regex=STAGING_REGEX)

    async with client_for(app) as client:
        local = await client.get("/health", headers={"Origin": "http://localhost:5173"})
        staging = await client.get("/health", headers={"Origin": ALLOWED_STAGING[0]})
        other = await client.get("/health", headers={"Origin": "https://evil.example"})

    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert staging.headers["access-control-allow-origin"] == ALLOWED_STAGING[0]
    assert "access-control-allow-origin" not in other.headers


async def test_a_refusal_from_a_pattern_origin_still_carries_the_cors_headers_to_be_readable():
    app = build_app(cors_allow_localhost=True)

    async with client_for(app) as client:
        response = await client.post(
            "/documents/analyze",
            files={"file": ("a.pdf", b"%PDF-1.4")},
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


# --- the startup check -----------------------------------------------------------


def cors_problems(**overrides):
    return [problem for problem in validate_settings(make_config(**overrides)) if "CORS" in problem]


def test_the_defaults_and_the_documented_values_are_valid():
    assert cors_problems() == []
    assert cors_problems(cors_allow_localhost=True, cors_origin_regex=STAGING_REGEX) == []
    assert cors_problems(cors_allow_localhost=False, cors_origin_regex="") == []


@pytest.mark.parametrize("pattern", ["https://[unclosed", "(", "*", "https://(?P<x"])
def test_a_pattern_that_is_not_a_regular_expression_is_reported_without_showing_it(pattern):
    problems = cors_problems(cors_origin_regex=pattern)

    assert problems and all("CORS_ORIGIN_REGEX" in problem for problem in problems)
    assert not any(pattern in problem for problem in problems)


@pytest.mark.parametrize(
    "pattern",
    [".*", ".+", "https?://.*", "(?i).*", "https://.+", ".*[.]azurestaticapps[.]net", r"\S+", "[^ ]+", "http.*"],
)
def test_a_pattern_that_would_allow_unrelated_sites_is_refused_at_startup(pattern):
    problems = cors_problems(cors_origin_regex=pattern)

    assert any("CORS_ORIGIN_REGEX" in problem and "too permissive" in problem for problem in problems)
    assert not any(pattern in problem for problem in problems)


def test_a_very_long_pattern_is_refused():
    problems = cors_problems(cors_origin_regex="https://a" + "b" * 600 + "[.]test")

    assert any("CORS_ORIGIN_REGEX" in problem and "500" in problem for problem in problems)


@pytest.mark.parametrize("value", [None, "yes please", 3])
def test_a_switch_that_is_not_a_boolean_is_reported(value):
    assert any("CORS_ALLOW_LOCALHOST" in problem for problem in cors_problems(cors_allow_localhost=value))


def test_the_wildcard_in_the_exact_list_is_still_refused():
    assert any("CORS_ORIGINS must not contain" in problem for problem in cors_problems(cors_origins=["*"]))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("false", False), ("0", False), ("", False), (None, False), ("maybe", None)],
)
def test_the_switch_is_read_like_the_other_boolean_settings(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("CORS_ALLOW_LOCALHOST", raising=False)
    else:
        monkeypatch.setenv("CORS_ALLOW_LOCALHOST", raw)

    assert parse_bool("CORS_ALLOW_LOCALHOST", False) is expected


def test_the_real_environment_variables_are_read_into_the_settings():
    script = (
        f"import sys; sys.path.insert(0, {str(APP_DIR)!r});"
        "from config.settings import settings, validate_settings;"
        "print(settings.cors_allow_localhost, settings.cors_origin_regex);"
        "print([p for p in validate_settings(settings) if 'CORS' in p])"
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "CORS_ALLOW_LOCALHOST": "true",
        "CORS_ORIGIN_REGEX": STAGING_REGEX,
        "CORS_ORIGINS": FRONT_ORIGIN,
    }
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, env=env, check=True)

    first, second = result.stdout.strip().splitlines()
    assert first == f"True {STAGING_REGEX}"
    assert second == "[]"


def test_with_no_variables_set_the_real_settings_allow_only_the_listed_origins():
    script = (
        f"import sys; sys.path.insert(0, {str(APP_DIR)!r});"
        "from config.settings import settings, build_origin_regex;"
        "print(settings.cors_allow_localhost, repr(settings.cors_origin_regex));"
        "print(build_origin_regex(settings.cors_allow_localhost, settings.cors_origin_regex))"
    )
    env = {"PATH": "/usr/bin:/bin"}  # no CORS_* variable at all
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, env=env, check=True)

    assert result.stdout.strip().splitlines() == ["False ''", "None"]
