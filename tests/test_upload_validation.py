import fitz
import pytest

from service.documentLlmAnalyzeService import LLMAnalyzerService
from tests.limits_support import (
    CHAT_URL,
    FRONT_ORIGIN,
    OCR_URL,
    analyze,
    chat_reply,
    distinct_pdf,
    make_limits_config,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)
from tests.test_auth import mint

ONE_MB = 1024 * 1024


@pytest.fixture
def greenpt(respx_mock):
    """GreenPT answers normally; the tests then check whether it was called at all."""
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply())
    ocr = respx_mock.post(OCR_URL).respond(json={"document": {"text": "OCR"}})
    return chat, ocr


@pytest.fixture
def pymupdf_must_not_open(monkeypatch):
    """Fails the test if the application opens any PDF with PyMuPDF."""

    def refuse(*args, **kwargs):
        raise AssertionError("PyMuPDF was reached")

    monkeypatch.setattr(fitz, "open", refuse)


def assert_no_paid_call(greenpt) -> None:
    chat, ocr = greenpt
    assert chat.call_count == 0
    assert ocr.call_count == 0


# --- size ---------------------------------------------------------------------


async def test_upload_far_above_the_limit_is_refused_with_413_before_the_application_reads_it(
    greenpt, pymupdf_must_not_open
):
    # 1 MB limit, plus 1 MB of multipart allowance: a 3 MB body is refused up front.
    async with running_app(make_limits_config(max_file_size_mb=1)) as (_, client):
        response = await analyze(client, b"%PDF-" + b"0" * (3 * ONE_MB))

    assert response.status_code == 413
    assert response.json() == {"detail": "File too large: the limit is 1 MB"}
    assert_no_paid_call(greenpt)


async def test_chunked_upload_without_a_content_length_is_refused_with_413_once_it_is_too_big(
    greenpt, pymupdf_must_not_open
):
    # A valid multipart body sent in chunks, so it has no Content-Length header.
    async def body():
        yield (
            b"--xyz\r\n"
            b'Content-Disposition: form-data; name="file"; filename="issue.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n%PDF-"
        )
        for _ in range(3):
            yield b"0" * ONE_MB
        yield b"\r\n--xyz--\r\n"

    async with running_app(make_limits_config(max_file_size_mb=1)) as (_, client):
        response = await client.post(
            "/documents/analyze",
            content=body(),
            headers={
                "Authorization": f"Bearer {mint(sub=42)}",
                "Content-Type": "multipart/form-data; boundary=xyz",
            },
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "File too large: the limit is 1 MB"}
    assert_no_paid_call(greenpt)


async def test_file_slightly_above_the_limit_is_refused_with_413_by_the_exact_size_check(
    greenpt, pymupdf_must_not_open
):
    # 1.5 MB is under limit + allowance, so it gets past the early check and is
    # stopped by the exact check while it is being read.
    async with running_app(make_limits_config(max_file_size_mb=1)) as (_, client):
        response = await analyze(client, b"%PDF-" + b"0" * int(1.5 * ONE_MB))

    assert response.status_code == 413
    assert response.json() == {"detail": "File too large: the limit is 1 MB"}
    assert_no_paid_call(greenpt)


async def test_file_exactly_at_the_size_limit_is_not_refused_for_its_size(greenpt):
    data = distinct_pdf(1)
    limit_mb = len(data) // ONE_MB + 1
    async with running_app(make_limits_config(max_file_size_mb=limit_mb)) as (_, client):
        response = await analyze(client, data)

    assert response.status_code == 200


async def test_413_answer_carries_the_cors_headers_so_the_browser_can_read_it(greenpt):
    async with running_app(make_limits_config(max_file_size_mb=1)) as (_, client):
        response = await analyze(
            client, b"%PDF-" + b"0" * (3 * ONE_MB), Origin=FRONT_ORIGIN
        )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == FRONT_ORIGIN


# --- not a usable PDF ---------------------------------------------------------


async def test_text_file_renamed_to_pdf_is_refused_with_415_and_nothing_is_paid(greenpt):
    async with running_app() as (_, client):
        response = await analyze(client, b"Ceci n'est pas un PDF.\n" * 50)

    assert response.status_code == 415
    assert response.json() == {"detail": "Only PDF files are accepted"}
    assert_no_paid_call(greenpt)


async def test_corrupt_pdf_with_a_valid_signature_is_refused_with_422_not_500(greenpt):
    # PyMuPDF repairs this junk into a document with no pages.
    async with running_app() as (_, client):
        response = await analyze(client, b"%PDF-1.4\n1 0 obj << /Broken >> endobj\n" + b"\x00" * 200)

    assert response.status_code == 422
    assert response.json() == {"detail": "The PDF has no pages"}
    assert_no_paid_call(greenpt)


async def test_pdf_that_pymupdf_cannot_open_is_refused_with_422_not_500(greenpt, monkeypatch):
    data = distinct_pdf(2)  # built before PyMuPDF is made to fail

    def cannot_open(*args, **kwargs):
        raise RuntimeError("cannot open broken document")

    monkeypatch.setattr(fitz, "open", cannot_open)

    async with running_app() as (_, client):
        response = await analyze(client, data)

    assert response.status_code == 422
    assert response.json() == {"detail": "The PDF could not be read"}
    assert_no_paid_call(greenpt)


async def test_password_protected_pdf_is_refused_with_422(greenpt):
    doc = fitz.open()
    doc.new_page().insert_text((36, 36), "secret", fontsize=8)
    protected = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="user-pw", owner_pw="owner-pw"
    )
    doc.close()

    async with running_app() as (_, client):
        response = await analyze(client, protected)

    assert response.status_code == 422
    assert response.json() == {"detail": "The PDF is password protected"}
    assert_no_paid_call(greenpt)


# --- pages and model calls ----------------------------------------------------


async def test_pdf_over_the_page_limit_is_refused_with_422_and_nothing_is_paid(greenpt):
    async with running_app(make_limits_config(max_pages=3)) as (_, client):
        response = await analyze(client, build_multi_page_pdf(4))

    assert response.status_code == 422
    assert response.json() == {"detail": "The PDF has 4 pages; the limit is 3"}
    assert_no_paid_call(greenpt)


async def test_pdf_exactly_at_the_page_limit_is_analysed(greenpt):
    async with running_app(make_limits_config(max_pages=3)) as (_, client):
        response = await analyze(client, distinct_pdf(7, pages=3))

    assert response.status_code == 200
    assert greenpt[0].call_count == 1


async def test_document_needing_more_model_calls_than_allowed_is_refused_before_any_chat_call(
    greenpt, monkeypatch
):
    # Shrink the single-call window and the chunk size so this document needs
    # 1 chunk per ~200 characters, i.e. far more than 3 model calls.
    monkeypatch.setattr(LLMAnalyzerService, "SINGLE_CALL_TOKEN_LIMIT", 100)
    monkeypatch.setattr(LLMAnalyzerService, "MAP_CHUNK_TOKEN_BUDGET", 50)

    async with running_app(make_limits_config(max_llm_calls=3)) as (_, client):
        response = await analyze(client, distinct_pdf(3))

    assert response.status_code == 422
    assert response.json()["detail"].endswith("and the limit is 3")
    assert greenpt[0].call_count == 0


async def test_document_that_fits_in_one_model_call_is_allowed_with_a_limit_of_one(greenpt):
    async with running_app(make_limits_config(max_llm_calls=1)) as (_, client):
        response = await analyze(client, distinct_pdf(4))

    assert response.status_code == 200
    assert greenpt[0].call_count == 1


def build_multi_page_pdf(pages: int) -> bytes:
    doc = fitz.open()
    for number in range(pages):
        doc.new_page().insert_text((36, 36), f"Page {number}", fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data
