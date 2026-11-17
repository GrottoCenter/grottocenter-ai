import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException

from config.settings import UsageLimits
from repository.usage import UsageRepository, day_key

logger = logging.getLogger(__name__)

# What a client is told to wait when it has too many analyses running at once.
CONCURRENCY_RETRY_AFTER_SECONDS = 10
# A counter document is kept for two days after its day starts, then MongoDB's TTL
# index removes it. The day in the document id is what makes a new day a fresh counter.
COUNTER_LIFETIME = timedelta(days=2)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConcurrencyLimiter:
    """How many analyses each user has running in this process.

    In memory on purpose: the server runs as a single instance, and a slot only lives as
    long as the request that holds it, so a restart loses nothing worth keeping.
    """

    def __init__(self) -> None:
        self._running: dict[str, int] = {}

    def acquire(self, key: str, limit: int) -> bool:
        if self._running.get(key, 0) >= limit:
            return False
        self._running[key] = self._running.get(key, 0) + 1
        return True

    def release(self, key: str) -> None:
        remaining = self._running.get(key, 0) - 1
        if remaining > 0:
            self._running[key] = remaining
        else:
            self._running.pop(key, None)

    def running(self, key: str) -> int:
        return self._running.get(key, 0)


def seconds_until_next_utc_midnight(now: datetime) -> int:
    tomorrow = datetime.combine(
        now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc
    )
    return max(1, int((tomorrow - now).total_seconds()))


class UsageService:
    """Decides whether one more paid analysis may start, and keeps count.

    Three limits, checked in this order so that an abusive user is turned away without
    touching anything shared: how many analyses the user has running, the user's daily
    quota, and the daily cap across all users.
    """

    def __init__(
        self,
        db,
        limits: UsageLimits,
        limiter: ConcurrencyLimiter,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = UsageRepository(db)
        self.limits = limits
        self.limiter = limiter
        self.clock = clock

    @asynccontextmanager
    async def metered(self, caller_id):
        """Hold one analysis slot for the duration of the `async with` block.

        Raises HTTPException 429 (the user's limits) or 503 (the global cap) before the
        block runs. The concurrency slot is always released. The daily counts are never
        given back when the analysis later fails: the cost (OCR, LLM calls) may already
        have been paid, and a refund would let a failing file be retried without bound.
        """
        if caller_id is None:
            raise HTTPException(status_code=401, detail="The caller could not be identified")
        key = str(caller_id)
        exempt = self.limits.is_exempt(caller_id)

        if not self.limiter.acquire(key, self.limits.user_max_concurrent):
            logger.warning("analysis refused caller=%s reason=concurrency", key)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many analyses in progress ({self.limits.user_max_concurrent} "
                    "at most). Wait for one to finish."
                ),
                headers={"Retry-After": str(CONCURRENCY_RETRY_AFTER_SECONDS)},
            )
        try:
            await self._consume_daily_counts(key, exempt)
            yield
        finally:
            self.limiter.release(key)

    async def _consume_daily_counts(self, key: str, exempt: bool = False) -> None:
        now = self.clock()
        day = day_key(now)
        expires_at = datetime.combine(now.date(), time.min) + COUNTER_LIFETIME
        retry_after = str(seconds_until_next_utc_midnight(now))

        user_counter = f"user:{key}:{day}"
        global_counter = f"global:{day}"

        if exempt:
            # No user counter at all: there is no limit to count against.
            logger.info("analysis quota exempt caller=%s", key)
        else:
            user_allowed = await asyncio.to_thread(
                self.repository.consume,
                user_counter,
                self.limits.user_daily_limit,
                {"scope": "user", "subject": key, "day": day, "expiresAt": expires_at},
            )
            if not user_allowed:
                logger.warning("analysis refused caller=%s reason=daily_quota", key)
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Daily analysis limit reached ({self.limits.user_daily_limit} per "
                        "day). Try again after midnight UTC."
                    ),
                    headers={"Retry-After": retry_after},
                )

        global_allowed = await asyncio.to_thread(
            self.repository.consume,
            global_counter,
            self.limits.global_daily_limit,
            {"scope": "global", "day": day, "expiresAt": expires_at},
        )
        if not global_allowed:
            # The user was not served, so the quota they were just charged goes back.
            if not exempt:
                await asyncio.to_thread(self.repository.release, user_counter)
            logger.error("analysis refused caller=%s reason=global_cap", key)
            raise HTTPException(
                status_code=503,
                detail="The daily analysis capacity has been reached. Try again tomorrow.",
                headers={"Retry-After": retry_after},
            )
