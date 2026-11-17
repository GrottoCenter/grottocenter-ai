"""A publication date is as precise as the document says: a year, a month or a day."""

import json
import logging

import pytest

from model.DocumentMetadata import DocumentAnalyseMetadata, DocumentMetadata
from model.PublicationDate import normalize_publication_date
from service.documentLlmAnalyzeService import LLMAnalyzerService
from tests.limits_support import (
    CHAT_URL,
    analyze,
    chat_reply,
    distinct_pdf,
    running_app,
    sso_secret,  # noqa: F401 - autouse fixture
)

# What GreenPT really answered for a 14-page article of the journal Endins (production log of
# the first smoke test): the model gave a bare year, because the article states nothing more.
ENDINS_ANSWER = {
    "title": "Noves aportacions a l'estudi de les cavitats de Cala Falcó – Cala Varques (Manacor, Mallorca)",
    "authors": [
        "Francesc Gràcia",
        "Pere Gamundí",
        "Bernat Clamor",
        "Miquel Trias",
        "Joan J. Fornós",
        "Mateu Febrer",
        "Jaume Pocoví",
    ],
    "publisher": "Endins",
    "publication_date": "2010",
    "identifiers": ["ISSN 0211-2515"],
    "languages": ["cat"],
    "descriptions": ["El coneixement de les coves litorals situades entre cala Falcó i cala Varques."],
    "grottocenter_type": "article",
    "rights": [],
    "articles": None,
}


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        pytest.param("2010", "2010", id="a year"),
        pytest.param(2010, "2010", id="a year given as a number"),
        pytest.param("2010-05", "2010-05", id="a month"),
        pytest.param("2010-5", "2010-05", id="a month without its leading zero"),
        pytest.param("2010-05-12", "2010-05-12", id="a day"),
        pytest.param("2010-5-2", "2010-05-02", id="a day without leading zeros"),
        pytest.param("2010-05-12T10:30:00Z", "2010-05-12", id="a full timestamp keeps its day"),
        pytest.param("  2010  ", "2010", id="surrounding spaces"),
        pytest.param("Juin 2010", "2010", id="text with one year keeps the year"),
        pytest.param("Mallorca, 2010", "2010", id="a place and a year"),
        pytest.param("2010-13", "2010", id="an impossible month keeps the year"),
        pytest.param("2010-02-30", "2010", id="an impossible day keeps the year"),
        pytest.param("2009/2010", None, id="two different years are ambiguous"),
        pytest.param("99999999999", None, id="a huge number"),
        pytest.param("99999999999-1", None, id="a huge number in a range"),
        pytest.param("1066", None, id="a year before the first printed journals"),
        pytest.param("3010", None, id="a year in the far future"),
        pytest.param("n.d.", None, id="no date"),
        pytest.param("", None, id="an empty string"),
        pytest.param(None, None, id="null"),
        pytest.param(True, None, id="a boolean"),
        pytest.param(["2010"], None, id="a list"),
    ],
)
def test_publication_date_is_normalised_to_year_month_or_day(given, expected):
    assert normalize_publication_date(given) == expected


def test_both_metadata_models_accept_a_year_only_publication_date():
    assert DocumentAnalyseMetadata.model_validate({"publication_date": "2010"}).publication_date == "2010"
    assert DocumentMetadata.model_validate({"publication_date": "2010"}).publication_date == "2010"


def test_the_model_is_told_which_date_formats_are_accepted():
    # The JSON schema is embedded in the prompt, so its description is the instruction.
    assert "YYYY-MM-DD" in LLMAnalyzerService.SCHEMA_BLOCK
    assert "never invent a month or a day" in LLMAnalyzerService.SCHEMA_BLOCK


async def test_the_answer_that_failed_in_production_is_analysed_and_keeps_its_year(respx_mock):
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(ENDINS_ANSWER)))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(1))

    assert response.status_code == 200
    [document] = response.json()["document_metadata"]
    assert document["publication_date"] == "2010"
    assert document["title"] == ENDINS_ANSWER["title"]
    assert document["authors"][0] == "Francesc Gràcia" and len(document["authors"]) == 7
    assert document["languages"] == ["cat"]
    assert document["grottocenter_type"] == "article"
    assert document["identifiers"] == ["ISSN 0211-2515"]


async def test_an_answer_with_an_unknown_type_and_licence_keeps_its_other_fields(respx_mock):
    answer = dict(ENDINS_ANSWER, grottocenter_type="essay", rights=["CC BY 4.0"])
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(answer)))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(2))

    assert response.status_code == 200
    [document] = response.json()["document_metadata"]
    assert document["grottocenter_type"] is None
    assert document["rights"] == []
    assert document["title"] == ENDINS_ANSWER["title"]
    assert document["publication_date"] == "2010"


async def test_an_answer_with_a_field_of_the_wrong_type_drops_only_that_field(respx_mock):
    answer = dict(ENDINS_ANSWER, authors="Francesc Gràcia, Pere Gamundí", publisher={"name": "Endins"})
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(answer)))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(3))

    assert response.status_code == 200
    [document] = response.json()["document_metadata"]
    assert document["authors"] == []
    assert document["publisher"] is None
    assert document["title"] == ENDINS_ANSWER["title"]


async def test_an_issue_keeps_its_valid_articles_when_one_article_is_invalid(respx_mock):
    answer = dict(
        ENDINS_ANSWER,
        grottocenter_type="issue",
        articles=[
            {"title": "First", "authors": ["A"], "page_start": 3, "page_end": 10},
            {"title": "Broken", "authors": ["B"], "page_start": "abc", "page_end": 20},
            {"title": "Third", "authors": ["C"], "page_start": 21, "page_end": 30},
        ],
    )
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(answer)))

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(4))

    assert response.status_code == 200
    documents = response.json()["document_metadata"]
    assert [d["title"] for d in documents[1:]] == ["First", "Third"]
    assert [d["pages"] for d in documents[1:]] == ["3-10", "21-30"]


async def test_an_answer_that_is_not_an_object_gets_a_502_not_a_500(respx_mock):
    # The article-shaped JSON is buried in prose the parser cannot use as an object.
    respx_mock.post(CHAT_URL).respond(json={"choices": [{"message": {"content": '{"title": ["not", "a", "title"]}'}}]})

    async with running_app() as (_app, client):
        response = await analyze(client, distinct_pdf(5))

    # A bad title is a droppable field, so this is still a usable (empty) analysis.
    assert response.status_code == 200
    assert response.json()["document_metadata"][0]["title"] is None


def test_validation_that_cannot_be_repaired_is_reported_as_an_upstream_error():
    from errors import UpstreamError
    from service.documentService import DocumentService

    with pytest.raises(UpstreamError):
        DocumentService.map_document_analysis_to_metadata(["not", "an", "object"])


async def test_the_model_answer_is_not_written_to_the_log_at_info_level(respx_mock, caplog):
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(ENDINS_ANSWER)))

    with caplog.at_level(logging.INFO):
        async with running_app() as (_app, client):
            response = await analyze(client, distinct_pdf(6))

    assert response.status_code == 200
    assert "Noves aportacions" not in caplog.text
    assert "Francesc Gràcia" not in caplog.text
    assert "El coneixement de les coves" not in caplog.text
    assert "prompt_tokens" in caplog.text  # the usage is still logged


async def test_the_model_answer_is_still_available_in_the_log_at_debug_level(respx_mock, caplog):
    respx_mock.post(CHAT_URL).respond(json=chat_reply(json.dumps(ENDINS_ANSWER)))

    with caplog.at_level(logging.DEBUG):
        async with running_app() as (_app, client):
            await analyze(client, distinct_pdf(7))

    assert "Noves aportacions" in caplog.text
