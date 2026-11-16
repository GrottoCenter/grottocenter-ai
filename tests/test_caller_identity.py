import logging

import httpx
import pytest

import main
from controller.documentController import get_document_service
from controller.documentController import process_document as analyze_route
from service.documentService import DocumentService
from tests.conftest import FakeAnalyzer
from tests.test_auth import SECRET, mint

ANALYSIS_LOGGER = "service.documentService"


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "sso_salt_documents", SECRET)


@pytest.fixture
def analyzer() -> FakeAnalyzer:
    return FakeAnalyzer({"title": "Single document", "grottocenter_type": "book"})


@pytest.fixture
def client(analyzer, mongo_repository):
    """The real app, with the analysis service wired to fakes (no GreenPT, no Mongo)."""
    main.app.dependency_overrides[get_document_service] = lambda: DocumentService(
        analyzer, mongo_repository
    )
    transport = httpx.ASGITransport(app=main.app)
    yield httpx.AsyncClient(transport=transport, base_url="http://test")
    main.app.dependency_overrides.clear()


def analysis_lines(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == ANALYSIS_LOGGER and record.getMessage().startswith("analysis ")
    ]


async def test_route_hands_the_token_subject_to_the_service_as_caller_id(make_upload, long_text_pdf):
    class RecordingService:
        def __init__(self):
            self.calls = []

        async def process_document(self, file, caller_id=None):
            self.calls.append(caller_id)
            return {"message": "success"}

    service = RecordingService()

    await analyze_route(
        make_upload(long_text_pdf), caller={"sub": 42, "aud": "documents"}, service=service
    )

    assert service.calls == [42]


async def test_analysis_without_a_token_is_rejected_and_nothing_runs(
    client, analyzer, mongo_db, long_text_pdf
):
    response = await client.post(
        "/documents/analyze", files={"file": ("issue.pdf", long_text_pdf, "application/pdf")}
    )

    assert response.status_code == 401
    assert analyzer.analyzed_texts == []
    assert mongo_db["documents"].count_documents({}) == 0


async def test_analysis_with_a_valid_token_logs_the_caller_and_never_the_token(
    client, long_text_pdf, caplog
):
    caplog.set_level(logging.INFO)
    token = mint()

    response = await client.post(
        "/documents/analyze",
        files={"file": ("issue.pdf", long_text_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    (line,) = analysis_lines(caplog)
    assert line.startswith("analysis caller=42 hash=")
    assert " pages=1 " in line
    assert " source=analyzed" in line
    assert "duration_ms=" in line
    assert token not in caplog.text
    assert SECRET not in caplog.text


async def test_repeat_upload_is_logged_as_served_from_storage_with_the_same_hash(
    client, long_text_pdf, caplog
):
    caplog.set_level(logging.INFO)
    request = {
        "files": {"file": ("issue.pdf", long_text_pdf, "application/pdf")},
        "headers": {"Authorization": f"Bearer {mint()}"},
    }

    await client.post("/documents/analyze", **request)
    await client.post("/documents/analyze", **request)

    first, second = analysis_lines(caplog)
    assert " source=analyzed" in first
    assert " source=storage" in second
    assert first.split(" hash=")[1].split(" ")[0] == second.split(" hash=")[1].split(" ")[0]
    assert "caller=42" in second
