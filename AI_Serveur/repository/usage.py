from datetime import datetime
from typing import Any

from pymongo.errors import DuplicateKeyError


class UsageRepository:
    """Per-day counters, one MongoDB document each.

    Counters live in MongoDB, not in memory, so a redeploy or a restart does not hand
    everybody a fresh quota. The `expiresAt` TTL index (created by scripts/init_db.py)
    deletes old days.
    """

    COLLECTION_NAME = "usage"

    def __init__(self, db):
        self.db = db

    @property
    def collection(self):
        return self.db[self.COLLECTION_NAME]

    def consume(self, counter_id: str, limit: int, fields: dict[str, Any]) -> bool:
        """Add one to the counter unless it already reached `limit`. True if it was added.

        The check and the increment are one conditional update, so concurrent requests
        can never push a counter past its limit. `_id` is unique, which is what makes
        the upsert safe: when the counter is at its limit the filter does not match, the
        upsert tries to insert the same `_id` and fails with DuplicateKeyError.
        """
        under_limit = {"_id": counter_id, "count": {"$lt": limit}}
        try:
            self.collection.update_one(
                under_limit,
                {"$inc": {"count": 1}, "$setOnInsert": fields},
                upsert=True,
            )
            return True
        except DuplicateKeyError:
            # Either the counter is at its limit, or two first requests of the day raced
            # to create it and this one lost. Telling them apart takes one more
            # conditional update, without upsert.
            result = self.collection.update_one(under_limit, {"$inc": {"count": 1}})
            return result.matched_count == 1

    def release(self, counter_id: str) -> None:
        """Take one back from a counter (never below zero)."""
        self.collection.update_one(
            {"_id": counter_id, "count": {"$gt": 0}}, {"$inc": {"count": -1}}
        )

    def count(self, counter_id: str) -> int:
        document = self.collection.find_one({"_id": counter_id}, {"count": 1})
        return int(document["count"]) if document else 0


def day_key(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")
