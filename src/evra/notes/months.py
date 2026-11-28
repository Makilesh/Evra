"""A month's short form read as the month, for the name check (BUILD.md §7.5, `notes/validate`):
the check reads a claim and everything it is checked against through `months_written_out`, so
"Oct 14" in one and "October 14" in the other are one date."""

from __future__ import annotations

import re

# A month's short form right beside a day or a year is that month (RC19): "Oct 14", "Oct 14th",
# "14 Oct", "Oct 2026". Without a number it may be a name ("Jan said..."). May has no short form.
_MONTH_NAMES = "january february march april june july august september october november december"
_MONTHS = {name[:3]: name for name in _MONTH_NAMES.split()} | {"sept": "september"}
_SHORT_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))  # "sept" before "sep"
_DAY = r"(?:3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?"
_MONTH_THEN_NUMBER = re.compile(rf"\b({_SHORT_MONTH})(?=\s+(?:{_DAY}|\d{{4}})\b)", re.IGNORECASE)
_DAY_THEN_MONTH = re.compile(rf"(\b{_DAY}\s+)({_SHORT_MONTH})\b", re.IGNORECASE)


def _spelled(short: str) -> str:
    month = _MONTHS[short.lower()]
    return month.capitalize() if short[0].isupper() else month


def months_written_out(text: str) -> str:
    """The text with each month's short form that stands beside a day or a year written out
    ("Oct 14" → "October 14", "14 sept" → "14 september"), for the name check: on both sides,
    "Oct 14" and "October 14" are one date (RC19)."""
    text = _MONTH_THEN_NUMBER.sub(lambda m: _spelled(m.group(1)), text)
    return _DAY_THEN_MONTH.sub(lambda m: m.group(1) + _spelled(m.group(2)), text)
