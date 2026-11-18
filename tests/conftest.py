import io
import json
import logging
from typing import Any

import fitz
import mongomock
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from repository.mongo import MongoRepository
from service.documentService import DocumentService
from tracing import JsonFormatter, TraceIdFilter

ISSUE_ANALYSIS: dict[str, Any] = {
    "title": "Spelunca 12",
    "authors": ["A. Martin"],
    "publisher": "FFS",
    "publication_date": "2024-03-01",
    "identifiers": ["ISSN 0242-1771"],
    "languages": ["fra"],
    "descriptions": ["Revue de la fédération"],
    "grottocenter_type": "issue",
    "rights": ["CC-BY-SA"],
    "articles": [
        {
            "title": "Gouffre X",
            "authors": ["B. Durand"],
            "page_start": 3,
            "page_end": 10,
        },
        {"title": "Cavité Y", "authors": [], "page_start": 11, "page_end": 14},
    ],
}


class FakeAnalyzer:
    """Stands in for LLMAnalyzerService and records what the service asks of it."""

    def __init__(self, analysis: dict[str, Any], ocr_text: str = "OCR TEXT") -> None:
        self.analysis = analysis
        self.ocr_text = ocr_text
        self.analyzed_texts: list[str] = []
        self.ocr_filenames: list[str] = []

    async def analyze_document(self, document_text: str) -> dict[str, Any]:
        self.analyzed_texts.append(document_text)
        return self.analysis

    async def get_text_with_OCR(  # noqa: N802 - mirrors LLMAnalyzerService
        self, pdf_content: bytes, filename: str
    ) -> str:
        self.ocr_filenames.append(filename)
        return self.ocr_text


def build_pdf(lines: list[str]) -> bytes:
    """One-page PDF with one line of text per entry."""
    doc = fitz.open()
    page = doc.new_page()
    for index, line in enumerate(lines):
        page.insert_text((36, 36 + 12 * index), line, fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def long_text_pdf() -> bytes:
    """A PDF whose extracted text is well above the 1000 character OCR threshold."""
    return build_pdf([f"Line {i:02d}: " + "stalactite " * 6 for i in range(40)])


@pytest.fixture
def short_text_pdf() -> bytes:
    return build_pdf(["Spelunca 12"])


@pytest.fixture
def blank_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def make_upload():
    def factory(data: bytes, filename: str = "issue.pdf") -> UploadFile:
        return UploadFile(
            file=io.BytesIO(data),
            filename=filename,
            headers=Headers({"content-type": "application/pdf"}),
        )

    return factory


@pytest.fixture
def mongo_db():
    return mongomock.MongoClient()["grottocenter_test"]


@pytest.fixture
def mongo_repository(mongo_db) -> MongoRepository:
    return MongoRepository(db=mongo_db)


@pytest.fixture
def fake_analyzer() -> FakeAnalyzer:
    return FakeAnalyzer({"title": "Single document", "grottocenter_type": "book"})


@pytest.fixture
def service(fake_analyzer, mongo_repository) -> DocumentService:
    return DocumentService(fake_analyzer, mongo_repository)


@pytest.fixture
def log_lines():
    """The JSON lines the application logs, as dicts, at INFO."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceIdFilter())
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    def lines() -> list[dict]:
        return [json.loads(line) for line in stream.getvalue().splitlines() if line]

    yield lines
    root.removeHandler(handler)
    root.setLevel(previous)
