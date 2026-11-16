import pytest

from tests.conftest import ISSUE_ANALYSIS, FakeAnalyzer


async def test_text_rich_pdf_is_analysed_without_ocr(
    service, fake_analyzer, make_upload, long_text_pdf
):
    await service.process_document(make_upload(long_text_pdf))

    assert fake_analyzer.ocr_filenames == []
    assert len(fake_analyzer.analyzed_texts) == 1
    assert "--- Page 1 ---" in fake_analyzer.analyzed_texts[0]
    assert "stalactite" in fake_analyzer.analyzed_texts[0]


async def test_pdf_with_little_text_goes_through_ocr_and_the_ocr_text_is_analysed(
    service, fake_analyzer, make_upload, short_text_pdf
):
    await service.process_document(make_upload(short_text_pdf))

    assert len(fake_analyzer.ocr_filenames) == 1
    assert fake_analyzer.ocr_filenames[0].endswith(".pdf")
    assert len(fake_analyzer.analyzed_texts) == 1
    assert "Spelunca 12" in fake_analyzer.analyzed_texts[0]
    assert "OCR TEXT" in fake_analyzer.analyzed_texts[0]


async def test_pdf_with_no_text_and_empty_ocr_raises_value_error_and_stores_nothing(
    mongo_repository, make_upload, blank_pdf
):
    from service.documentService import DocumentService

    analyzer = FakeAnalyzer({"title": "never used"}, ocr_text="")
    service = DocumentService(analyzer, mongo_repository)

    with pytest.raises(ValueError, match="No text could be extracted"):
        await service.process_document(make_upload(blank_pdf))

    assert analyzer.analyzed_texts == []
    assert mongo_repository.db["documents"].count_documents({}) == 0


async def test_empty_upload_raises_value_error_before_any_analysis_or_storage(
    service, fake_analyzer, mongo_db, make_upload
):
    with pytest.raises(ValueError, match="Uploaded file is empty"):
        await service.process_document(make_upload(b""))

    assert fake_analyzer.analyzed_texts == []
    assert fake_analyzer.ocr_filenames == []
    assert mongo_db["documents"].count_documents({}) == 0


async def test_new_pdf_is_stored_with_hash_mime_type_model_and_page_count(
    service, mongo_db, make_upload, long_text_pdf
):
    result = await service.process_document(make_upload(long_text_pdf))

    stored = list(mongo_db["documents"].find({}, {"_id": 0}))
    assert len(stored) == 1
    assert stored[0]["fileName"] == result["filename"]
    assert len(stored[0]["hash"]) == 64
    assert stored[0]["mimeType"] == "application/pdf"
    assert stored[0]["model"] == "GreenPT"
    assert stored[0]["metadata"]["title"] == "Single document"
    assert stored[0]["metadata"]["formats"] == ["application/pdf"]
    assert stored[0]["metadata"]["pages"] == "1"


async def test_issue_analysis_stores_one_mongo_document_per_issue_and_article(
    mongo_db, mongo_repository, make_upload, long_text_pdf
):
    from service.documentService import DocumentService

    service = DocumentService(FakeAnalyzer(ISSUE_ANALYSIS), mongo_repository)

    result = await service.process_document(make_upload(long_text_pdf))

    stored = list(mongo_db["documents"].find({}, {"_id": 0}))
    assert [d["metadata"]["title"] for d in stored] == [
        "Spelunca 12",
        "Gouffre X",
        "Cavité Y",
    ]
    assert len({d["hash"] for d in stored}) == 1
    assert len(result["document_metadata"]) == 3


async def test_second_upload_of_the_same_bytes_returns_the_stored_result_without_analysis(
    service, fake_analyzer, mongo_db, make_upload, long_text_pdf
):
    first = await service.process_document(make_upload(long_text_pdf))
    second = await service.process_document(make_upload(long_text_pdf, "renamed.pdf"))

    assert len(fake_analyzer.analyzed_texts) == 1
    assert fake_analyzer.ocr_filenames == []
    assert second["filename"] == first["filename"]
    assert [m.title for m in second["document_metadata"]] == ["Single document"]
    assert mongo_db["documents"].count_documents({}) == 1


async def test_different_pdf_bytes_are_analysed_separately(
    service, fake_analyzer, mongo_db, make_upload, long_text_pdf, short_text_pdf
):
    await service.process_document(make_upload(long_text_pdf))
    await service.process_document(make_upload(short_text_pdf))

    assert len(fake_analyzer.analyzed_texts) == 2
    assert mongo_db["documents"].count_documents({}) == 2
