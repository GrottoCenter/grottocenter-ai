"""Reading what the language model answered, without losing all of it for one odd field.

The model is asked for a JSON object that fits the schema of DocumentAnalyseMetadata, and
it mostly does. When one field does not fit (a licence name that is not in the list, a
list where a string is expected), the rest of the answer is still good, and was paid for.
So the fields that do not fit are dropped, the rest is kept, and the names of the dropped
fields (never their values, which are document text) are logged. An answer that cannot be
repaired is an upstream failure (502), not a server error.
"""

import copy
import logging
from typing import Any

from pydantic import ValidationError

from errors import UpstreamError
from model.DocumentMetadata import DocumentAnalyseMetadata

logger = logging.getLogger(__name__)

MAX_LOGGED_NAME = 40


def validate_analysis(raw: Any) -> DocumentAnalyseMetadata:
    """The analysis metadata for the model's answer, with invalid fields dropped."""
    if isinstance(raw, DocumentAnalyseMetadata):
        return raw
    try:
        return DocumentAnalyseMetadata.model_validate(raw)
    except ValidationError as error:
        repaired, dropped = _drop_invalid_fields(raw, error)

    logger.warning(
        "The model's answer had fields that do not fit the schema, dropped: %s",
        ", ".join(sorted(dropped)),
    )
    try:
        return DocumentAnalyseMetadata.model_validate(repaired)
    except ValidationError as error:
        raise UpstreamError(
            "The model's answer is not usable even without its invalid fields"
        ) from error


def _drop_invalid_fields(raw: Any, error: ValidationError) -> tuple[dict, set[str]]:
    if not isinstance(raw, dict):
        raise UpstreamError("The model's answer is not a JSON object") from error

    data = copy.deepcopy(raw)
    dropped: set[str] = set()
    invalid_articles: set[int] = set()

    for problem in error.errors():
        location = problem["loc"]
        if not location:
            raise UpstreamError("The model's answer cannot be repaired") from error
        field = location[0]
        articles = data.get("articles")

        if field == "articles" and len(location) >= 2 and isinstance(location[1], int):
            index = location[1]
            entry = articles[index] if isinstance(articles, list) and index < len(articles) else None
            if problem["type"] == "extra_forbidden" and len(location) == 3 and isinstance(entry, dict):
                # An unknown key on an article: drop the key, keep the article.
                entry.pop(location[2], None)
                dropped.add(f"articles.{str(location[2])[:MAX_LOGGED_NAME]}")
            else:
                invalid_articles.add(index)
                dropped.add("articles[]")
        else:
            data.pop(field, None)
            dropped.add(str(field)[:MAX_LOGGED_NAME])

    if invalid_articles and isinstance(data.get("articles"), list):
        data["articles"] = [
            article for index, article in enumerate(data["articles"]) if index not in invalid_articles
        ]
    return data, dropped
