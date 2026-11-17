"""Some users have no daily quota: the list comes from QUOTA_EXEMPT_USER_IDS."""

import logging

import httpx
import mongomock
import pytest
from fastapi import HTTPException

from config.settings import UsageLimits, parse_user_ids, validate_settings
from tests.limits_support import (
    CHAT_URL,
    analyze,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tests.test_usage_limits import (
    EVENING,
    Clock,
    ConcurrencyLimiter,
    UsageService,
    counter,
    refusal,
    use_one_slot,
)

EXEMPT = frozenset({"1", "60181"})


@pytest.fixture
def clock() -> Clock:
    return Clock(EVENING)


@pytest.fixture
def db():
    return mongomock.MongoClient()["exempt_test"]


def make_usage(db, clock, **limits) -> UsageService:
    return UsageService(db, UsageLimits(**limits), ConcurrencyLimiter(), clock)


# --- reading the list from the environment ------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, frozenset(), id="unset"),
        pytest.param("", frozenset(), id="empty"),
        pytest.param("   ", frozenset(), id="blank"),
        pytest.param("1", frozenset({"1"}), id="one id"),
        pytest.param("1,60181", frozenset({"1", "60181"}), id="two ids"),
        pytest.param(" 1 , 60181 ,", frozenset({"1", "60181"}), id="spaces and a trailing comma"),
        pytest.param("1,1,60181", frozenset({"1", "60181"}), id="a repeated id"),
        pytest.param("007", frozenset({"7"}), id="leading zeros are not part of the id"),
    ],
)
def test_user_ids_are_read_from_a_comma_separated_variable(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("QUOTA_EXEMPT_USER_IDS", raising=False)
    else:
        monkeypatch.setenv("QUOTA_EXEMPT_USER_IDS", raw)

    assert parse_user_ids("QUOTA_EXEMPT_USER_IDS") == expected


@pytest.mark.parametrize(
    "raw",
    ["abc", "1,abc", "0", "-3", "1.5", "1;2", "1 2", "٣", "1,,x", ",".join(str(i) for i in range(1, 52))],
)
def test_a_value_that_is_not_a_list_of_user_ids_is_invalid(monkeypatch, raw):
    monkeypatch.setenv("QUOTA_EXEMPT_USER_IDS", raw)

    assert parse_user_ids("QUOTA_EXEMPT_USER_IDS") is None


def test_fifty_ids_are_accepted_and_fifty_one_are_not(monkeypatch):
    monkeypatch.setenv("QUOTA_EXEMPT_USER_IDS", ",".join(str(i) for i in range(1, 51)))
    assert len(parse_user_ids("QUOTA_EXEMPT_USER_IDS")) == 50


def test_startup_validation_names_the_variable_and_never_shows_its_value():
    problems = validate_settings(make_limits_config(quota_exempt_user_ids=None))

    assert any("QUOTA_EXEMPT_USER_IDS" in problem for problem in problems)
    assert not any("secret-looking-value" in problem for problem in problems)


def test_startup_validation_accepts_a_list_and_an_empty_list():
    assert validate_settings(make_limits_config(quota_exempt_user_ids=EXEMPT)) == []
    assert validate_settings(make_limits_config(quota_exempt_user_ids=frozenset())) == []
    assert validate_settings(make_limits_config()) == []


def test_the_limits_read_the_list_from_the_configuration():
    limits = UsageLimits.from_config(make_limits_config(quota_exempt_user_ids=EXEMPT))

    assert limits.quota_exempt_user_ids == EXEMPT
    assert UsageLimits().quota_exempt_user_ids == frozenset()


# --- who is exempt ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("caller", "expected"),
    [
        (1, True),
        ("1", True),
        (60181, True),
        ("60181", True),
        (10, False),
        (11, False),
        (100, False),
        (601810, False),
        (6018, False),
        (2, False),
        (None, False),
    ],
)
def test_a_user_is_exempt_only_when_the_whole_id_is_in_the_list(caller, expected):
    assert UsageLimits(quota_exempt_user_ids=EXEMPT).is_exempt(caller) is expected


def test_nobody_is_exempt_by_default():
    assert UsageLimits().is_exempt(1) is False


# --- what the exemption does, and does not do ------------------------------------


async def test_an_exempt_user_can_analyse_beyond_the_daily_quota(db, clock):
    usage = make_usage(db, clock, user_daily_limit=2, quota_exempt_user_ids=EXEMPT)

    for _ in range(6):
        await use_one_slot(usage, 1)
    for _ in range(6):
        await use_one_slot(usage, "60181")


async def test_other_users_keep_their_daily_quota_next_to_an_exempt_one(db, clock):
    usage = make_usage(db, clock, user_daily_limit=2, quota_exempt_user_ids=EXEMPT)
    for _ in range(5):
        await use_one_slot(usage, 1)

    await use_one_slot(usage, 2)
    await use_one_slot(usage, 2)
    refused = await refusal(usage, 2)

    assert refused.status_code == 429
    assert "Daily analysis limit reached (2 per day)" in refused.detail


async def test_a_user_whose_id_starts_with_an_exempt_id_is_not_exempt(db, clock):
    usage = make_usage(db, clock, user_daily_limit=1, quota_exempt_user_ids=EXEMPT)

    for user in (10, 100, 601810):
        await use_one_slot(usage, user)
        assert (await refusal(usage, user)).status_code == 429


async def test_an_exempt_user_leaves_no_daily_counter_behind(db, clock):
    usage = make_usage(db, clock, user_daily_limit=2, quota_exempt_user_ids=EXEMPT)

    for _ in range(3):
        await use_one_slot(usage, 1)

    assert counter(db, "user:1:2026-11-16") == 0
    assert counter(db, "global:2026-11-16") == 3


async def test_an_exempt_analysis_still_counts_toward_the_global_cap(db, clock):
    usage = make_usage(db, clock, user_daily_limit=2, global_daily_limit=3, quota_exempt_user_ids=EXEMPT)
    for _ in range(3):
        await use_one_slot(usage, 1)

    refused = await refusal(usage, 1)

    assert refused.status_code == 503
    assert counter(db, "global:2026-11-16") == 3
    assert (await refusal(usage, 2)).status_code == 503


async def test_an_exempt_user_is_still_limited_to_the_concurrent_analyses(db, clock):
    usage = make_usage(db, clock, user_max_concurrent=1, quota_exempt_user_ids=EXEMPT)

    async with usage.metered(1):
        refused = await refusal(usage, 1)

    assert refused.status_code == 429
    assert "Too many analyses in progress" in refused.detail
    await use_one_slot(usage, 1)


async def test_an_unidentified_caller_is_refused_even_when_a_list_of_exempt_users_exists(db, clock):
    usage = make_usage(db, clock, quota_exempt_user_ids=EXEMPT)

    with pytest.raises(HTTPException) as refused:
        async with usage.metered(None):
            pass

    assert refused.value.status_code == 401


async def test_an_exempt_analysis_is_logged_as_such_without_any_document_content(db, clock, caplog):
    usage = make_usage(db, clock, quota_exempt_user_ids=EXEMPT)

    with caplog.at_level(logging.INFO):
        await use_one_slot(usage, 60181)

    assert "analysis quota exempt caller=60181" in caplog.text


# --- through the whole application -----------------------------------------------


async def test_through_http_an_exempt_user_is_not_stopped_by_the_daily_quota_and_others_are(respx_mock):
    respx_mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=chat_reply()))
    config = make_limits_config(user_daily_limit=2, quota_exempt_user_ids=frozenset({"1"}))

    async with running_app(config) as (_app, client):
        exempt = [(await analyze(client, distinct_pdf(i), user=1)).status_code for i in range(1, 5)]
        ordinary = [(await analyze(client, distinct_pdf(i), user=2)).status_code for i in range(10, 13)]
        refused = await analyze(client, distinct_pdf(13), user=2)

    assert exempt == [200, 200, 200, 200]
    assert ordinary[:2] == [200, 200]
    assert ordinary[2] == 429
    assert refused.status_code == 429
    assert "Retry-After" in refused.headers
