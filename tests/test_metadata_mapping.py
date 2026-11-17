import pytest

from model.GrottocenterType import GrottocenterType
from model.LicenseName import LicenseName
from service.documentService import DocumentService
from tests.conftest import ISSUE_ANALYSIS


def test_analysis_without_articles_maps_to_a_single_document():
    result = DocumentService.map_document_analysis_to_metadata(
        {
            "title": "Atlas des grottes",
            "authors": ["C. Petit"],
            "grottocenter_type": "book",
            "identifiers": ["ISBN 978-2-0000-0000-0"],
            "articles": None,
        }
    )

    assert len(result) == 1
    assert result[0].title == "Atlas des grottes"
    assert result[0].authors == ["C. Petit"]
    assert result[0].grottocenter_type == GrottocenterType.BOOK
    assert result[0].identifiers == ["ISBN 978-2-0000-0000-0"]
    assert result[0].parent is None
    assert result[0].pages is None


def test_issue_with_two_articles_maps_to_the_issue_followed_by_its_articles():
    result = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)

    assert [d.title for d in result] == ["Spelunca 12", "Gouffre X", "Cavité Y"]


def test_issue_document_keeps_its_own_identifiers_and_has_no_parent_or_pages():
    issue = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[0]

    assert issue.grottocenter_type == GrottocenterType.ISSUE
    assert issue.identifiers == ["ISSN 0242-1771"]
    assert issue.parent is None
    assert issue.pages is None


def test_article_documents_are_typed_article_and_point_to_the_issue_title():
    articles = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[1:]

    assert [a.grottocenter_type for a in articles] == [GrottocenterType.ARTICLE] * 2
    assert [a.parent for a in articles] == ["Spelunca 12", "Spelunca 12"]


def test_article_pages_are_formatted_as_start_dash_end():
    articles = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[1:]

    assert [a.pages for a in articles] == ["3-10", "11-14"]


def test_article_authors_come_from_the_article_not_the_issue():
    articles = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[1:]

    assert articles[0].authors == ["B. Durand"]
    assert articles[1].authors == []


def test_article_documents_do_not_inherit_the_issue_identifiers():
    articles = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[1:]

    assert [a.identifiers for a in articles] == [[], []]


def test_article_documents_share_the_issue_publisher_date_language_and_rights():
    articles = DocumentService.map_document_analysis_to_metadata(ISSUE_ANALYSIS)[1:]

    for article in articles:
        assert article.publisher == "FFS"
        assert article.publication_date == "2024-03-01"
        assert article.languages == ["fra"]
        assert article.rights == [LicenseName.CC_BY_SA]
        assert article.descriptions == ["Revue de la fédération"]


def test_null_lists_from_the_llm_become_empty_lists():
    result = DocumentService.map_document_analysis_to_metadata(
        {"title": "Sans listes", "authors": None, "languages": None, "rights": None}
    )

    assert result[0].authors == []
    assert result[0].languages == []
    assert result[0].rights == []


@pytest.mark.parametrize(
    ("first", "last", "expected"),
    [
        (3, 10, "3-10"),
        (3, None, "3"),
        (None, 10, "10"),
        (None, None, None),
        (0, 0, "0-0"),
    ],
)
def test_page_range_never_contains_the_word_none(first, last, expected):
    assert DocumentService.page_range(first, last) == expected


def test_an_article_without_page_numbers_gets_no_pages_instead_of_none_none():
    documents = DocumentService.map_document_analysis_to_metadata(
        {
            "title": "Issue 12",
            "grottocenter_type": "issue",
            "articles": [{"title": "Without pages", "authors": ["A"], "page_start": None, "page_end": None}],
        }
    )

    assert [d.title for d in documents] == ["Issue 12", "Without pages"]
    assert documents[1].pages is None
