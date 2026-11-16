"""Helpers for the tests of the cost and abuse limits: a whole application wired to fakes."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import mongomock
import pytest

from application import create_app
from tests.conftest import build_pdf
from tests.test_auth import SECRET, mint

BASE_URL = "https://greenpt.test/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
OCR_URL = f"{BASE_URL}/tools/documents/convert/file"
FRONT_ORIGIN = "https://grottocenter.org"


def chat_reply(content: str = '{"title": "Un document", "grottocenter_type": "book"}') -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def make_limits_config(**overrides) -> SimpleNamespace:
    """A valid configuration whose limits are the production defaults, unless overridden."""
    values = {
        "api_key": "dummy-greenpt-key",
        "greenpt_api_url": BASE_URL,
        "sso_salt_documents": SECRET,
        "mongo_uri": "mongodb://mongo.test:27017",
        "mongo_db_name": "grottocenter_test",
        "cors_origins": [FRONT_ORIGIN],
        "log_level": "INFO",
        "analyze_enabled": True,
        "user_daily_limit": 5,
        "user_max_concurrent": 2,
        "global_daily_limit": 200,
        "max_file_size_mb": 50,
        "max_pages": 300,
        "max_llm_calls": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SharedMongo:
    """One mongomock server that any number of application instances connect to.

    Two applications built on the same SharedMongo see the same data, the way two
    process lifetimes see the same MongoDB.
    """

    def __init__(self) -> None:
        self.server = mongomock.MongoClient()

    def __call__(self, uri: str, **kwargs):
        server = self.server

        class Client:
            admin = SimpleNamespace(command=lambda name: {"ok": 1.0})

            def __getitem__(self, database_name: str):
                return server[database_name]

            def close(self) -> None:
                pass

        return Client()

    def database(self, name: str = "grottocenter_test"):
        return self.server[name]


@pytest.fixture(autouse=True)
def sso_secret(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "sso_salt_documents", SECRET)


@asynccontextmanager
async def running_app(config=None, mongo: SharedMongo | None = None):
    """The real application, lifespan included, with an HTTP client wired to it."""
    config = config or make_limits_config()
    mongo = mongo or SharedMongo()
    app = create_app(config, mongo)
    async with app.router.lifespan_context(app):
        # raise_app_exceptions=False: an unhandled error in the app is a 500 response, as in production.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield app, client


def distinct_pdf(number: int, pages: int = 1) -> bytes:
    """A PDF with enough text to skip OCR, different for each `number` (so a different hash)."""
    doc_lines = [f"Document {number} line {i:02d}: " + "stalactite " * 6 for i in range(40)]
    if pages == 1:
        return build_pdf(doc_lines)
    import fitz

    doc = fitz.open()
    for page_number in range(pages):
        page = doc.new_page()
        page.insert_text((36, 36), f"Document {number} page {page_number}", fontsize=8)
        for index, line in enumerate(doc_lines):
            page.insert_text((36, 50 + 12 * index), line, fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


async def analyze(client: httpx.AsyncClient, data: bytes, user: int = 42, **headers):
    """POST a PDF to the analysis endpoint with a token for `user`."""
    headers = {"Authorization": f"Bearer {mint(sub=user)}", **headers}
    return await client.post(
        "/documents/analyze",
        files={"file": ("issue.pdf", data, "application/pdf")},
        headers=headers,
    )
