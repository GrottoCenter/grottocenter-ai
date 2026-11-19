import httpx
import pytest

from client.GreenPT import GreenPTClient
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.documentService import DocumentService

BASE_URL = "https://greenpt.test/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
OCR_URL = f"{BASE_URL}/tools/documents/convert/file"


def chat_reply(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


@pytest.fixture
async def greenpt_service(mongo_db):
    async with httpx.AsyncClient(base_url=BASE_URL) as http_client:
        client = GreenPTClient(BASE_URL, "test-key", http_client=http_client)
        yield DocumentService(LLMAnalyzerService(client), MongoRepository(db=mongo_db))


async def test_text_pdf_triggers_one_chat_call_with_the_expected_request_and_parses_the_reply(
    greenpt_service, respx_mock, make_upload, long_text_pdf
):
    chat = respx_mock.post(CHAT_URL).respond(
        json=chat_reply('{"title": "Gouffre de la Henne Morte", "grottocenter_type": "book"}')
    )
    ocr = respx_mock.post(OCR_URL)

    result = await greenpt_service.process_document(make_upload(long_text_pdf))

    assert chat.call_count == 1
    assert not ocr.called
    body = httpx.Response(200, content=chat.calls[0].request.content).json()
    assert body["model"] == "mistral-small-3.2-24b-instruct-2506"
    assert body["temperature"] == 0
    assert body["stream"] is False
    assert body["messages"][0]["role"] == "system"
    assert "stalactite" in body["messages"][1]["content"]
    assert [m.title for m in result["document_metadata"]] == ["Gouffre de la Henne Morte"]


async def test_scanned_pdf_calls_ocr_first_then_analyses_the_ocr_text(
    greenpt_service, respx_mock, make_upload, short_text_pdf
):
    ocr = respx_mock.post(OCR_URL).respond(json={"document": {"text": "Texte reconnu par OCR"}})
    chat = respx_mock.post(CHAT_URL).respond(json=chat_reply('{"title": "Scan"}'))

    await greenpt_service.process_document(make_upload(short_text_pdf))

    assert ocr.call_count == 1
    assert chat.call_count == 1
    sent = httpx.Response(200, content=chat.calls[0].request.content).json()
    assert "Texte reconnu par OCR" in sent["messages"][1]["content"]


async def test_reply_wrapped_in_markdown_fences_is_still_parsed(
    greenpt_service, respx_mock, make_upload, long_text_pdf
):
    respx_mock.post(CHAT_URL).respond(
        json=chat_reply('```json\n{"title": "Dans une clôture"}\n```')
    )

    result = await greenpt_service.process_document(make_upload(long_text_pdf))

    assert [m.title for m in result["document_metadata"]] == ["Dans une clôture"]


async def test_reply_that_is_not_json_yields_empty_metadata_with_the_page_count(
    greenpt_service, respx_mock, make_upload, long_text_pdf
):
    respx_mock.post(CHAT_URL).respond(json=chat_reply("Désolé, je ne peux pas répondre."))

    result = await greenpt_service.process_document(make_upload(long_text_pdf))

    metadata = result["document_metadata"][0]
    assert metadata.title is None
    assert metadata.authors == []
    assert metadata.pages == "1"
