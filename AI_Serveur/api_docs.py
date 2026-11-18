"""What the public API documentation says: the schemas and the text of every answer.

The documentation is public on purpose, so it describes the API and nothing else: it must
not name the application, the framework or a library behind it (see tests/test_api_documentation.py).
"""

from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field

from model.DocumentMetadata import DocumentMetadata

API_TITLE = "Document metadata API"
API_VERSION = "0.2.0"
API_DESCRIPTION = (
    "Extracts the bibliographic metadata of a PDF document: title, authors, publication "
    "date, type, licence and, for an issue, the articles it contains. A document that was "
    "analysed before is answered from storage."
)

BEARER_SCHEME_NAME = "bearerAuth"
BEARER_DESCRIPTION = (
    "A short-lived token for this API, not the user's own token. Get one from the "
    "Grottocenter API with `POST /api/v1/sso/auth-token`, sending the user's token as "
    'a bearer token and `{"product": "documents"}` as the JSON body. The token it '
    "returns is valid for 30 seconds: ask for a new one before each request."
)

ANALYZE_SUMMARY = "Analyze a PDF document"
ANALYZE_OPERATION_ID = "analyzeDocument"
ANALYZE_DESCRIPTION = (
    "Reads a PDF and returns its metadata: one object for the document and, when it is an "
    "issue made of articles, one more per article.\n\n"
    "The request is `multipart/form-data` with one field, `file`: a PDF, within the size "
    "and page limits of the service. A scanned document (no text layer) is read with OCR, "
    "which takes longer. An analysis can last more than a minute.\n\n"
    "Every error has the same body, `{\"detail\": \"<message>\"}`: use the status code, not "
    "the message, to decide what to do."
)


class AnalyzeUpload(BaseModel):
    """The multipart body of the analysis request."""

    file: UploadFile = Field(description="The PDF to analyse.")


class AnalyzeResponse(BaseModel):
    """The answer to a successful analysis."""

    message: str = Field(description="Always `success`.")
    filename: str = Field(
        description="Name under which the file is stored on the server. It is not the name of the uploaded file."
    )
    document_metadata: list[DocumentMetadata] = Field(
        description=(
            "The metadata of the document, first, then those of its articles, in the order "
            "of the document. A document that is not an issue gives a list of one."
        )
    )


class ErrorResponse(BaseModel):
    """The body of every error."""

    detail: str = Field(description="A short description of what went wrong, in English.")


ANALYZE_EXAMPLE: dict[str, Any] = {
    "message": "success",
    "filename": "00000000-0000-0000-0000-0000000f4240.pdf",
    "document_metadata": [
        {
            "title": "Spelunca 12",
            "authors": ["A. Martin"],
            "publisher": "FFS",
            "publication_date": "2024-03",
            "identifiers": ["ISSN 0242-1771"],
            "languages": ["fra"],
            "descriptions": ["Revue de la fédération"],
            "grottocenter_type": "issue",
            "rights": ["CC-BY-SA"],
            "formats": [],
            "sources": [],
            "parent": None,
            "pages": None,
        }
    ],
}

TRACE_ID_HEADER = {
    "X-Trace-Id": {
        "description": (
            "Identifier of this request, to quote in a report. Send your own as a UUID in the "
            "request header of the same name to follow one user action across services."
        ),
        "schema": {"type": "string", "format": "uuid"},
    }
}

RETRY_AFTER = {
    "Retry-After": {
        "description": "Seconds to wait before trying again.",
        "schema": {"type": "string", "example": "3600"},
    }
}


def _error(description: str, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "headers": {**TRACE_ID_HEADER, **(headers or {})},
    }


ANALYZE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "model": AnalyzeResponse,
        "description": "The metadata of the document.",
        "headers": TRACE_ID_HEADER,
        "content": {"application/json": {"example": ANALYZE_EXAMPLE}},
    },
    401: _error("The token is missing, malformed, expired, or was issued for another product."),
    413: _error("The upload is larger than the size limit. It is refused before it is read."),
    415: _error("The file is not a PDF."),
    422: _error(
        "The upload cannot be analysed: the request has no `file` field, the file is empty, "
        "password protected, unreadable, has no pages or too many pages, contains no text "
        "(even after OCR), or needs more model calls than allowed."
    ),
    429: _error(
        "The user reached the daily limit of analyses, or has too many analyses running at "
        "once. Try again after `Retry-After` seconds.",
        headers=RETRY_AFTER,
    ),
    500: _error("An unexpected error. The cause is in the server's log, not in the answer."),
    502: _error("The analysis service failed or gave an unusable answer. Try again later."),
    503: _error(
        "The service is not taking analyses: the daily capacity of the service is reached "
        "(with `Retry-After`) or analysis is switched off (without it).",
        headers=RETRY_AFTER,
    ),
    504: _error("The analysis service did not answer in time. Try again later."),
}
