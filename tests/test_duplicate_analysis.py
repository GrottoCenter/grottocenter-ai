"""One file is analysed and stored once, however many requests arrive for it."""

import asyncio
import json

import httpx
import pytest
from pymongo.errors import BulkWriteError, DuplicateKeyError

from repository.mongo import MongoRepository
from scripts.init_db import DOCUMENTS_VALIDATOR, ensure_document_indexes
from service.analysisLocks import HashLocks
from service.documentService import DocumentService
from tests.conftest import ISSUE_ANALYSIS, FakeAnalyzer
from tests.limits_support import (
    CHAT_URL,
    SharedMongo,
    analyze,
    chat_reply,
    distinct_pdf,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)


def slow_greenpt(respx_mock, content: str | None = None):
    """A GreenPT chat endpoint slow enough for concurrent requests to overlap."""
    reply = chat_reply() if content is None else chat_reply(content)

    async def answer(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=reply)

    return respx_mock.post(CHAT_URL).mock(side_effect=answer)


def counters(mongo: SharedMongo) -> dict[str, int]:
    usage = mongo.database()["usage"]
    return {doc["_id"].rsplit(":", 1)[0]: doc["count"] for doc in usage.find()}


def stored_positions(mongo: SharedMongo) -> list[int]:
    documents = mongo.database()["documents"]
    return sorted(doc["position"] for doc in documents.find())


# --- two requests at once ---------------------------------------------------


async def test_two_simultaneous_uploads_of_one_file_cost_one_analysis_and_store_one_set(
    respx_mock,
):
    chat = slow_greenpt(respx_mock)
    mongo = SharedMongo()
    data = distinct_pdf(1)

    async with running_app(mongo=mongo) as (_app, client):
        first, second = await asyncio.gather(
            analyze(client, data), analyze(client, data)
        )

    assert (first.status_code, second.status_code) == (200, 200)
    assert chat.call_count == 1
    assert stored_positions(mongo) == [0]
    assert first.json() == second.json()


async def test_simultaneous_uploads_of_an_issue_store_its_documents_once_in_order(respx_mock):
    chat = slow_greenpt(respx_mock, json.dumps(ISSUE_ANALYSIS))
    mongo = SharedMongo()
    data = distinct_pdf(2)

    async with running_app(mongo=mongo) as (_app, client):
        responses = await asyncio.gather(*[analyze(client, data) for _ in range(4)])

    assert [r.status_code for r in responses] == [200, 200, 200, 200]
    assert chat.call_count == 1
    assert stored_positions(mongo) == [0, 1, 2]
    titles = [[d["title"] for d in r.json()["document_metadata"]] for r in responses]
    assert titles == [["Spelunca 12", "Gouffre X", "Cavité Y"]] * 4
    assert len({json.dumps(r.json(), sort_keys=True) for r in responses}) == 1


async def test_the_request_that_waits_uses_no_quota_and_no_slot(respx_mock):
    slow_greenpt(respx_mock)
    mongo = SharedMongo()
    data = distinct_pdf(3)

    async with running_app(mongo=mongo) as (app, client):
        await asyncio.gather(
            analyze(client, data, user=42), analyze(client, data, user=7)
        )
        running_after = (
            app.state.concurrency.running("42"),
            app.state.concurrency.running("7"),
        )

    counts = counters(mongo)
    assert counts["global"] == 1
    assert sorted(counts.get(key, 0) for key in ("user:42", "user:7")) == [0, 1]
    assert running_after == (0, 0)


async def test_different_files_uploaded_together_are_each_analysed(respx_mock):
    chat = slow_greenpt(respx_mock)
    mongo = SharedMongo()

    async with running_app(mongo=mongo) as (_app, client):
        responses = await asyncio.gather(
            analyze(client, distinct_pdf(10)), analyze(client, distinct_pdf(11))
        )

    assert [r.status_code for r in responses] == [200, 200]
    assert chat.call_count == 2
    assert stored_positions(mongo) == [0, 0]


async def test_failed_analysis_releases_the_file_lock_so_a_retry_works(respx_mock):
    chat = respx_mock.post(CHAT_URL)
    chat.side_effect = [
        httpx.Response(500, text="down"),
        httpx.Response(200, json=chat_reply()),
    ]
    mongo = SharedMongo()
    data = distinct_pdf(4)

    async with running_app(mongo=mongo) as (app, client):
        failed = await analyze(client, data)
        locks_after_failure = len(app.state.analysis_locks)
        retried = await analyze(client, data)
        locks_after_retry = len(app.state.analysis_locks)

    assert failed.status_code == 502
    assert retried.status_code == 200
    assert (locks_after_failure, locks_after_retry) == (0, 0)
    assert stored_positions(mongo) == [0]


async def test_request_waiting_behind_a_failed_analysis_runs_its_own_analysis(respx_mock):
    calls = []

    async def first_fails_then_works(request):
        calls.append(request)
        await asyncio.sleep(0.05)
        if len(calls) == 1:
            return httpx.Response(500, text="down")
        return httpx.Response(200, json=chat_reply())

    chat = respx_mock.post(CHAT_URL).mock(side_effect=first_fails_then_works)
    data = distinct_pdf(5)

    async with running_app() as (_app, client):
        responses = await asyncio.gather(analyze(client, data), analyze(client, data))

    assert sorted(r.status_code for r in responses) == [200, 502]
    assert chat.call_count == 2


# --- the lock table ---------------------------------------------------------


async def test_hash_lock_is_gone_once_nobody_holds_or_waits_for_it():
    locks = HashLocks()

    async with locks.hold("a"):
        assert len(locks) == 1
    assert len(locks) == 0


async def test_hash_lock_is_released_when_the_holder_fails():
    locks = HashLocks()

    with pytest.raises(RuntimeError):
        async with locks.hold("a"):
            raise RuntimeError("analysis failed")

    assert len(locks) == 0
    async with locks.hold("a"):
        assert len(locks) == 1


async def test_hash_lock_table_does_not_grow_with_the_number_of_files():
    locks = HashLocks()

    for number in range(1000):
        async with locks.hold(f"hash-{number}"):
            pass

    assert len(locks) == 0


async def test_hash_lock_serialises_the_same_key_but_not_different_ones():
    locks = HashLocks()
    events: list[str] = []

    async def worker(key: str, name: str):
        async with locks.hold(key):
            events.append(f"{name} start")
            await asyncio.sleep(0.02)
            events.append(f"{name} end")

    await asyncio.gather(worker("a", "a1"), worker("a", "a2"), worker("b", "b1"))

    assert events.index("a1 end") < events.index("a2 start")
    assert events.index("b1 start") < events.index("a1 end")
    assert len(locks) == 0


async def test_hash_lock_is_released_when_a_waiting_request_is_cancelled():
    locks = HashLocks()
    release = asyncio.Event()

    async def holder():
        async with locks.hold("a"):
            await release.wait()

    async def waiter():
        async with locks.hold("a"):
            pass

    holding = asyncio.create_task(holder())
    await asyncio.sleep(0)
    waiting = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    release.set()
    await holding

    assert len(locks) == 0


# --- a second writer: the unique index and the duplicate key error ---------


class OtherWriterWinsRepository(MongoRepository):
    """Another instance stores the same analysis between this one's check and its insert."""

    def __init__(self, db, error: Exception, other_writer_documents: list[dict]):
        super().__init__(db)
        self.error = error
        self.other_writer_documents = other_writer_documents

    def insert_many(self, documents):
        if self.other_writer_documents:
            self.get_collection(self.COLLECTION_NAME).insert_many(self.other_writer_documents)
        raise self.error


def stored_document(file_hash: str, file_name: str, title: str, position: int) -> dict:
    from datetime import datetime, timezone

    from model.DocumentMetadata import DocumentMetadata

    metadata = DocumentMetadata(title=title, grottocenter_type="book").model_dump(mode="json")
    return {
        "fileName": file_name,
        "hash": file_hash,
        "mimeType": "application/pdf",
        "createdAt": datetime.now(timezone.utc),
        "model": "GreenPT",
        "metadata": metadata,
        "position": position,
    }


def duplicate_bulk_error() -> BulkWriteError:
    return BulkWriteError(
        {"writeErrors": [{"index": 0, "code": 11000, "errmsg": "E11000 duplicate key"}]}
    )


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(DuplicateKeyError("E11000 duplicate key"), id="DuplicateKeyError"),
        pytest.param(duplicate_bulk_error(), id="BulkWriteError with code 11000"),
    ],
)
async def test_duplicate_key_at_insert_time_answers_with_the_stored_result(
    error, mongo_db, make_upload, long_text_pdf
):
    file_hash = DocumentService.get_file_hash(long_text_pdf)
    repository = OtherWriterWinsRepository(
        mongo_db, error, [stored_document(file_hash, "other.pdf", "Stored by the other writer", 0)]
    )
    service = DocumentService(FakeAnalyzer(ISSUE_ANALYSIS), repository)

    result = await service.process_document(make_upload(long_text_pdf))

    assert result["filename"] == "other.pdf"
    assert [m.title for m in result["document_metadata"]] == ["Stored by the other writer"]
    assert mongo_db["documents"].count_documents({}) == 1


async def test_duplicate_key_with_nothing_stored_behind_it_is_not_hidden(
    mongo_db, make_upload, long_text_pdf
):
    repository = OtherWriterWinsRepository(mongo_db, DuplicateKeyError("E11000"), [])
    service = DocumentService(FakeAnalyzer(ISSUE_ANALYSIS), repository)

    with pytest.raises(DuplicateKeyError):
        await service.process_document(make_upload(long_text_pdf))


async def test_write_error_that_is_not_a_duplicate_is_not_mistaken_for_one(
    mongo_db, make_upload, long_text_pdf
):
    file_hash = DocumentService.get_file_hash(long_text_pdf)
    validation_error = BulkWriteError(
        {"writeErrors": [{"index": 0, "code": 121, "errmsg": "Document failed validation"}]}
    )
    repository = OtherWriterWinsRepository(
        mongo_db, validation_error, [stored_document(file_hash, "other.pdf", "x", 0)]
    )
    service = DocumentService(FakeAnalyzer(ISSUE_ANALYSIS), repository)

    with pytest.raises(BulkWriteError):
        await service.process_document(make_upload(long_text_pdf))


async def test_unique_index_refuses_a_second_document_at_the_same_position_of_a_file(mongo_db):
    ensure_document_indexes(mongo_db)
    documents = mongo_db["documents"]
    documents.insert_one(stored_document("h1", "a.pdf", "first", 0))

    with pytest.raises(DuplicateKeyError):
        documents.insert_one(stored_document("h1", "b.pdf", "second", 0))
    documents.insert_one(stored_document("h1", "a.pdf", "article", 1))
    documents.insert_one(stored_document("h2", "c.pdf", "other file", 0))

    assert documents.count_documents({}) == 3


async def test_creating_the_document_indexes_twice_is_harmless(mongo_db):
    ensure_document_indexes(mongo_db)
    ensure_document_indexes(mongo_db)

    index = mongo_db["documents"].index_information()["hash_position_unique"]
    assert index["unique"] is True
    assert index["key"] == [("hash", 1), ("position", 1)]
    # mongomock records this option but does not evaluate it. That documents stored before
    # `position` existed do not block the index is checked against a real MongoDB by hand.
    assert index["partialFilterExpression"] == {"position": {"$exists": True}}


def test_document_validator_accepts_a_position_as_an_integer():
    properties = DOCUMENTS_VALIDATOR["$jsonSchema"]["properties"]

    assert properties["position"] == {"bsonType": ["int", "long"]}
    assert "position" not in DOCUMENTS_VALIDATOR["$jsonSchema"]["required"]


async def test_stored_documents_are_read_back_in_upload_order(mongo_db):
    documents = mongo_db["documents"]
    documents.insert_many(
        [
            stored_document("h1", "a.pdf", "article 2", 2),
            stored_document("h1", "a.pdf", "the issue", 0),
            stored_document("h1", "a.pdf", "article 1", 1),
        ]
    )

    read = MongoRepository(mongo_db).get_with_hash("h1")

    assert [d.metadata.title for d in read] == ["the issue", "article 1", "article 2"]
    assert [d.position for d in read] == [0, 1, 2]
