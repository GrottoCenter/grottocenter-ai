"""A publication date as precise as the document states it: a year, a month or a day."""

import re
from datetime import date, datetime
from typing import Any, Optional

# Journals before 1500 do not exist and a year past 2100 is a typo, not a date. Outside this
# range a four-digit number is not read as a year.
MIN_YEAR = 1500
MAX_YEAR = 2100

_YEAR = re.compile(r"^(\d{4})$")
_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")
_YEAR_MONTH_DAY = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
_FOUR_DIGITS = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def _plausible(year: int) -> bool:
    return MIN_YEAR <= year <= MAX_YEAR


def _as_text(value: Any) -> Optional[str]:
    """The value as a stripped string, or None for anything that is not text or a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _exact(text: str) -> Optional[str]:
    """`YYYY`, `YYYY-MM` or `YYYY-MM-DD` (a time after the day is ignored), if it is valid."""
    if match := _YEAR_MONTH_DAY.match(text):
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat() if _plausible(year) else None
        except ValueError:
            return None
    if match := _YEAR_MONTH.match(text):
        year, month = (int(part) for part in match.groups())
        return f"{year:04d}-{month:02d}" if _plausible(year) and 1 <= month <= 12 else None
    if _YEAR.match(text):
        return text if _plausible(int(text)) else None
    return None


def _only_year(text: str) -> Optional[str]:
    """The year, if exactly one plausible year is written in the text."""
    years = {int(year) for year in _FOUR_DIGITS.findall(text) if _plausible(int(year))}
    return str(years.pop()) if len(years) == 1 else None


def normalize_publication_date(value: Any) -> Optional[str]:
    """Return `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, or None when no date can be read.

    The language model gives a bare year when that is all the document says, and
    Grottocenter stores the date as free text, so a year is a perfectly good date. Anything
    that is not one of the three shapes keeps its year when there is exactly one plausible
    year in it, and is dropped otherwise: a guess would end up in the catalogue.
    """
    text = _as_text(value)
    if text is None:
        return None
    return _exact(text) or _only_year(text)
