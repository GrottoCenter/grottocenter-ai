"""The detailed logs of the test phase, behind LOG_ANALYSIS_DETAILS.

With the switch on, the log also holds what is normally kept out of it because it comes
from the user's document: the original file name, the metadata returned, what the model
answered when its answer could not be used, and more of what GreenPT said when it failed.
With the switch off none of it is logged. It is meant for the test phase, before the front
end is live: turn it off (remove the variable) before real traffic.

The switch is read per request, from the configuration of the application that handles it
(see tracing.TraceIdMiddleware), so there is no global state.
"""

import json
import unicodedata
from contextvars import ContextVar
from typing import Any

# A log line travels through Docker's syslog driver and the VM's rsyslog, whose default maximum
# message size is 8 KB: a longer line is cut, and a cut JSON line cannot be read. The limits
# below keep a whole line, with its envelope and the escaping of quotes, under that size.
MAX_FILE_NAME = 200
RESULT_CHARACTERS = 5_000
RAW_ANSWER_CHARACTERS = 2_000
UPSTREAM_BODY_CHARACTERS = 2_000

details_enabled: ContextVar[bool] = ContextVar("log_analysis_details", default=False)


def enabled() -> bool:
    return details_enabled.get()


def clean_file_name(name: str | None) -> str:
    """A client's file name made safe to put in a log: one line, no control characters, cut.

    It is text to show, never to use: it is not turned into a path or a key anywhere.
    """
    if not name:
        return ""
    printable = "".join(
        " " if unicodedata.category(char).startswith("C") else char for char in str(name)
    )
    return " ".join(printable.split())[:MAX_FILE_NAME]


def cut(text: str, limit: int) -> tuple[str, bool]:
    """The text cut to `limit` characters, and whether it was cut."""
    return (text[:limit], len(text) > limit)


def as_json_text(value: Any, limit: int) -> tuple[str, bool]:
    return cut(json.dumps(value, ensure_ascii=False, default=str), limit)


# What identifies a document when the whole answer does not fit in a line: an issue with many
# articles repeats the same long description for each of them.
COMPACT_FIELDS = ("title", "grottocenter_type", "pages")


def result_for_log(documents: list[dict]) -> tuple[str, bool, bool]:
    """The answer as JSON text for one log line: (text, compact, truncated).

    The whole answer when it fits. Otherwise only the identifying fields of each document,
    which keeps the text valid JSON for the usual case (an issue and its articles). Only an
    answer that is too long even in that form is cut, and then it says so.
    """
    text, truncated = as_json_text(documents, RESULT_CHARACTERS)
    if not truncated:
        return text, False, False
    short = [{field: document.get(field) for field in COMPACT_FIELDS} for document in documents]
    text, truncated = as_json_text(short, RESULT_CHARACTERS)
    return text, True, truncated
