import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import mongomock
import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config.settings import UsageLimits
from repository.usage import UsageRepository
from service.usageService import ConcurrencyLimiter, UsageService
from tests.limits_support import (
    CHAT_URL,
    SharedMongo,
    analyze,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)

EVENING = datetime(2026, 11, 16, 21, 30, 0, tzinfo=timezone.utc)  # 2 h 30 before midnight UTC
NEXT_MORNING = datetime(2026, 11, 17, 0, 0, 1, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(EVENING)


@pytest.fixture
def db():
    return mongomock.MongoClient()["usage_test"]


def make_usage(db, clock, **limits) -> UsageService:
    return UsageService(db, UsageLimits(**limits), ConcurrencyLimiter(), clock)


async def use_one_slot(usage: UsageService, user) -> None:
    async with usage.metered(user):
        pass


async def refusal(usage: UsageService, user) -> HTTPException:
    with pytest.raises(HTTPException) as refused:
        await use_one_slot(usage, user)
    return refused.value


def counter(db, counter_id: str) -> int:
    return UsageRepository(db).count(counter_id)


# --- the daily quota, with a fixed clock --------------------------------------


async def test_sixth_analysis_of_the_day_is_refused_with_429_and_the_seconds_until_midnight_utc(
    db, clock
):
    usage = make_usage(db, clock, user_daily_limit=5)
    for _ in range(5):
        await use_one_slot(usage, 42)

    refused = await refusal(usage, 42)

    assert refused.status_code == 429
    assert refused.headers == {"Retry-After": "9000"}  # 2 h 30 min
    assert refused.detail == "Daily analysis limit reached (5 per day). Try again after midnight UTC."
    assert counter(db, "user:42:2026-11-16") == 5


async def test_another_user_is_not_affected_by_a_user_who_used_the_whole_quota(db, clock):
    usage = make_usage(db, clock, user_daily_limit=1)
    await use_one_slot(usage, 42)
    assert (await refusal(usage, 42)).status_code == 429

    await use_one_slot(usage, 43)

    assert counter(db, "user:43:2026-11-16") == 1


async def test_quota_starts_again_on_the_next_utc_day(db, clock):
    usage = make_usage(db, clock, user_daily_limit=1)
    await use_one_slot(usage, 42)
    assert (await refusal(usage, 42)).status_code == 429

    clock.now = NEXT_MORNING
    await use_one_slot(usage, 42)

    assert counter(db, "user:42:2026-11-17") == 1
    assert counter(db, "user:42:2026-11-16") == 1


async def test_analysis_without_a_known_caller_is_refused_with_401(db, clock):
    refused = await refusal(make_usage(db, clock), None)

    assert refused.status_code == 401


async def test_failed_analysis_does_not_give_its_count_back_but_releases_its_slot(db, clock):
    usage = make_usage(db, clock, user_daily_limit=2, user_max_concurrent=1)

    with pytest.raises(RuntimeError):
        async with usage.metered(42):
            raise RuntimeError("GreenPT failed after the OCR was paid for")

    assert counter(db, "user:42:2026-11-16") == 1
    assert usage.limiter.running("42") == 0
    await use_one_slot(usage, 42)  # the slot is free again
    assert (await refusal(usage, 42)).status_code == 429  # but the failed run was counted


# --- concurrency --------------------------------------------------------------


async def hold_a_slot(usage, user, started: asyncio.Event, finish: asyncio.Event) -> None:
    async with usage.metered(user):
        started.set()
        await finish.wait()


async def test_third_concurrent_analysis_of_a_user_is_refused_with_429_until_one_finishes(
    db, clock
):
    usage = make_usage(db, clock, user_daily_limit=10, user_max_concurrent=2)
    finish = asyncio.Event()
    started = [asyncio.Event(), asyncio.Event()]
    running = [
        asyncio.create_task(hold_a_slot(usage, 42, started[0], finish)),
        asyncio.create_task(hold_a_slot(usage, 42, started[1], finish)),
    ]
    await asyncio.gather(*(event.wait() for event in started))

    refused = await refusal(usage, 42)
    other_user_slot = asyncio.create_task(use_one_slot(usage, 43))

    assert refused.status_code == 429
    assert refused.headers == {"Retry-After": "10"}
    assert refused.detail == "Too many analyses in progress (2 at most). Wait for one to finish."
    await other_user_slot  # another user is not affected
    assert counter(db, "user:42:2026-11-16") == 2  # the refused attempt was not counted

    finish.set()
    await asyncio.gather(*running)
    await use_one_slot(usage, 42)
    assert counter(db, "user:42:2026-11-16") == 3


# --- the global cap -----------------------------------------------------------


async def test_global_cap_refuses_with_503_and_gives_the_users_count_back(db, clock):
    usage = make_usage(db, clock, global_daily_limit=2, user_daily_limit=5)
    await use_one_slot(usage, 1)
    await use_one_slot(usage, 2)

    refused = await refusal(usage, 3)

    assert refused.status_code == 503
    assert refused.headers == {"Retry-After": "9000"}
    assert refused.detail == "The daily analysis capacity has been reached. Try again tomorrow."
    assert counter(db, "user:3:2026-11-16") == 0  # not served, so not charged
    assert counter(db, "global:2026-11-16") == 2


async def test_user_over_the_quota_is_refused_without_touching_the_global_count(db, clock):
    usage = make_usage(db, clock, user_daily_limit=1, global_daily_limit=100)
    await use_one_slot(usage, 42)
    assert (await refusal(usage, 42)).status_code == 429

    assert counter(db, "global:2026-11-16") == 1


# --- the counter itself -------------------------------------------------------


def test_counter_stops_at_its_limit():
    repository = UsageRepository(mongomock.MongoClient()["counter_test"])

    results = [repository.consume("user:1:2026-11-16", 3, {"scope": "user"}) for _ in range(5)]

    assert results == [True, True, True, False, False]
    assert repository.count("user:1:2026-11-16") == 3


def test_concurrent_requests_can_never_push_a_counter_past_its_limit():
    repository = UsageRepository(mongomock.MongoClient()["race_test"])

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(
                lambda _: repository.consume("user:1:2026-11-16", 5, {"scope": "user"}),
                range(64),
            )
        )

    assert results.count(True) == 5
    assert repository.count("user:1:2026-11-16") == 5


class RacingCollection:
    """A collection whose first update loses the race to create the counter."""

    def __init__(self, real) -> None:
        self.real = real
        self.calls = 0

    def update_one(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise DuplicateKeyError("E11000 duplicate key error")
        return self.real.update_one(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.real, name)


def racing_repository(existing_count: int) -> tuple[UsageRepository, RacingCollection]:
    db = mongomock.MongoClient()["racing_test"]
    db["usage"].insert_one({"_id": "user:1:2026-11-16", "count": existing_count})
    collection = RacingCollection(db["usage"])
    repository = UsageRepository(db)
    repository.__class__ = type(
        "RacingUsageRepository", (UsageRepository,), {"collection": property(lambda self: collection)}
    )
    return repository, collection


def test_request_that_loses_the_race_to_create_the_counter_is_still_counted_when_under_the_limit():
    repository, _ = racing_repository(existing_count=1)

    assert repository.consume("user:1:2026-11-16", 5, {"scope": "user"}) is True
    assert repository.count("user:1:2026-11-16") == 2


def test_request_whose_counter_is_already_at_the_limit_is_refused_after_the_duplicate_key_error():
    repository, _ = racing_repository(existing_count=5)

    assert repository.consume("user:1:2026-11-16", 5, {"scope": "user"}) is False
    assert repository.count("user:1:2026-11-16") == 5


def test_giving_a_count_back_never_goes_below_zero():
    repository = UsageRepository(mongomock.MongoClient()["release_test"])
    repository.consume("user:1:2026-11-16", 5, {"scope": "user"})

    repository.release("user:1:2026-11-16")
    repository.release("user:1:2026-11-16")

    assert repository.count("user:1:2026-11-16") == 0


# --- the whole application ----------------------------------------------------


def stored_counts(mongo: SharedMongo) -> dict[str, int]:
    usage = mongo.database()["usage"]
    return {document["_id"].rsplit(":", 1)[0]: document["count"] for document in usage.find()}


@pytest.fixture
def greenpt(respx_mock):
    return respx_mock.post(CHAT_URL).respond(json=chat_reply())


async def test_sixth_analysis_of_the_day_over_http_gets_429_with_retry_after_while_another_user_is_served(
    greenpt,
):
    async with running_app(make_limits_config(user_daily_limit=5)) as (_, client):
        statuses = [(await analyze(client, distinct_pdf(n), user=42)).status_code for n in range(5)]
        sixth = await analyze(client, distinct_pdf(5), user=42)
        other_user = await analyze(client, distinct_pdf(6), user=43)

    assert statuses == [200] * 5
    assert sixth.status_code == 429
    assert 1 <= int(sixth.headers["retry-after"]) <= 86_400
    assert other_user.status_code == 200
    assert greenpt.call_count == 6  # the refused request never reached GreenPT


async def test_repeat_upload_of_an_analysed_file_is_served_from_storage_and_uses_no_quota(
    greenpt,
):
    data = distinct_pdf(1)
    mongo = SharedMongo()
    async with running_app(make_limits_config(user_daily_limit=1), mongo) as (_, client):
        first = await analyze(client, data)
        second = await analyze(client, data)
        third = await analyze(client, data)

    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 200]
    assert second.json()["filename"] == first.json()["filename"]
    assert greenpt.call_count == 1
    assert stored_counts(mongo) == {"user:42": 1, "global": 1}


async def test_kill_switch_answers_503_and_no_paid_call_is_made(greenpt):
    mongo = SharedMongo()
    async with running_app(make_limits_config(analyze_enabled=False), mongo) as (_, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 503
    assert response.json() == {"detail": "Document analysis is temporarily disabled"}
    assert greenpt.call_count == 0
    assert stored_counts(mongo) == {}


async def test_global_cap_answers_503_to_the_next_user_and_makes_no_paid_call(greenpt):
    mongo = SharedMongo()
    async with running_app(make_limits_config(global_daily_limit=1), mongo) as (_, client):
        served = await analyze(client, distinct_pdf(1), user=1)
        refused = await analyze(client, distinct_pdf(2), user=2)

    assert served.status_code == 200
    assert refused.status_code == 503
    assert "retry-after" in refused.headers
    assert greenpt.call_count == 1
    assert stored_counts(mongo) == {"user:1": 1, "user:2": 0, "global": 1}  # user 2 was charged, then refunded


async def test_quota_is_kept_when_the_application_is_created_again(greenpt):
    mongo = SharedMongo()
    config = make_limits_config(user_daily_limit=5)

    async with running_app(config, mongo) as (_, client):
        for n in range(5):
            assert (await analyze(client, distinct_pdf(n))).status_code == 200

    async with running_app(config, mongo) as (_, restarted_client):
        response = await analyze(restarted_client, distinct_pdf(5))

    assert response.status_code == 429
    assert greenpt.call_count == 5


async def test_third_concurrent_analysis_over_http_gets_429_and_the_slots_are_released(respx_mock):
    gate = asyncio.Event()
    in_flight = 0

    async def slow_reply(request):
        nonlocal in_flight
        in_flight += 1
        await gate.wait()
        return httpx.Response(200, json=chat_reply())

    respx_mock.post(CHAT_URL).mock(side_effect=slow_reply)

    async with running_app(make_limits_config(user_max_concurrent=2)) as (app, client):
        first = asyncio.create_task(analyze(client, distinct_pdf(1)))
        second = asyncio.create_task(analyze(client, distinct_pdf(2)))
        for _ in range(200):
            if in_flight == 2:
                break
            await asyncio.sleep(0.01)
        assert in_flight == 2

        third = await analyze(client, distinct_pdf(3))
        gate.set()
        finished = [await first, await second]
        fourth = await analyze(client, distinct_pdf(4))

        assert app.state.concurrency.running("42") == 0

    assert third.status_code == 429
    assert third.headers["retry-after"] == "10"
    assert [response.status_code for response in finished] == [200, 200]
    assert fourth.status_code == 200


async def test_analysis_that_fails_in_greenpt_frees_its_slot_but_keeps_its_count(respx_mock):
    chat = respx_mock.post(CHAT_URL)
    chat.side_effect = [
        httpx.Response(500, text="GreenPT is down"),
        httpx.Response(200, json=chat_reply()),
    ]
    mongo = SharedMongo()
    config = make_limits_config(user_max_concurrent=1, user_daily_limit=2)

    async with running_app(config, mongo) as (app, client):
        failed = await analyze(client, distinct_pdf(1))
        assert app.state.concurrency.running("42") == 0
        served = await analyze(client, distinct_pdf(2))
        refused = await analyze(client, distinct_pdf(3))

    assert failed.status_code == 502
    assert served.status_code == 200
    assert refused.status_code == 429  # the failed run used one of the two
    assert stored_counts(mongo)["user:42"] == 2
