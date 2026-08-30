"""
Shoot Day Code Normalization.

Evidence:
- references/domain/identity-rules.md
- references/domain/grain-and-entities.md
"""
import re
from typing import Any, Dict, Optional


def normalize_shoot_day(raw_day: Optional[str]) -> Optional[str]:
    """
    Folds shoot day representations (SD31, D031, #31, 260728_SD31) into canonical integer string.
    
    Examples:
    - 'SD31', 'D031', '#31', '260728_SD31', '31' -> '31'
    """
    if not raw_day or not isinstance(raw_day, str):
        return None

    cleaned = raw_day.strip().upper()
    if not cleaned:
        return None

    # 1. Prioritize explicit shoot day prefixes: SD31, D031, #31, _SD31_
    match = re.search(r"(?:SD|D|#)0*(\d+)", cleaned)
    if match:
        return str(int(match.group(1)))

    # 2. Fall back to standalone numeric day
    if cleaned.isdigit():
        return str(int(cleaned))

    match_digits = re.search(r"\b0*(\d+)\b", cleaned)
    if match_digits:
        return str(int(match_digits.group(1)))

    return cleaned


# --------------------------------------------------------------------------- #
# The calendar date a shoot day happened on
# --------------------------------------------------------------------------- #
#
# A shoot day is a number and a date is a date, and nothing bound the two until
# Francisco named where the binding is written (2026-08-30):
#
#   "You can find the shooting date in the daily production report on the top
#    of the page... but you can find it also in the Thumbnail Report
#    (260728_SD31 -> 28 July - 2026). Also on every script report on the header
#    (Date: 28/07/2026). Also on the sound csv header... So to find the
#    shooting date you should look at the Thumbnail Report, because it's the
#    most reliable one."
#
# Sources are tried in his order of reliability, and the one that answered is
# returned with the date. Which document said so is not decoration: five
# documents state this date and they can disagree, and a date with no source is
# a number nobody can check.

# `260728_SD31` -- the Silverstack volume name. The most reliable source
# because it is the only one that states the date and the shoot day *together*,
# so the two cannot be paired wrongly.
_VOLUME_STAMP = re.compile(r"\b(\d{2})(\d{2})(\d{2})_SD(\d+)\b", re.IGNORECASE)

# `Date: 28/07/2026` or `DATE: 28/07/26` -- script reports and the daily
# production report.
_LABELLED = re.compile(
    r"\bDATE\s*[:\-]?\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})\b",
    re.IGNORECASE,
)

# A bare `28/07/2026` anywhere in a header.
_BARE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?!\d)")

# `DemoProduction-2026-7-28_CAM_A.csv` -- the camera reports carry it only here.
_FILENAME = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


def _iso(day: int, month: int, year: int) -> Optional[str]:
    """A date, or None where the numbers cannot be one."""
    if year < 100:
        year += 2000
    if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 < year < 2200):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_shoot_date(text: str = "", filename: str = "") -> Optional[Dict[str, Any]]:
    """
    The calendar date a document says its shoot day happened on.

    Returns `{"date": "2026-07-28", "source": ..., "shoot_day": "31" | None}`,
    or None when the document states no date. None rather than a guess: a
    document that does not say what day it covers has not said it, and
    inventing one would put every take on the wrong date.

    Only the header is read -- the first stretch of the document -- because a
    date further down belongs to a row, not to the report. A facing page
    carries dates from across the schedule and the last one on it is not the
    day it was filed.
    """
    header = (text or "")[:1200]
    joined = f"{filename or ''}\n{header}"

    stamp = _VOLUME_STAMP.search(joined)
    if stamp:
        year, month, day = stamp.group(1), stamp.group(2), stamp.group(3)
        # YYMMDD, so 260728 is 2026-07-28.
        iso = _iso(int(day), int(month), int(year))
        if iso:
            return {"date": iso, "source": "volume_stamp", "shoot_day": str(int(stamp.group(4)))}

    for pattern, source in ((_LABELLED, "labelled_header"), (_BARE, "header")):
        found = pattern.search(header)
        if found:
            iso = _iso(int(found.group(1)), int(found.group(2)), int(found.group(3)))
            if iso:
                return {"date": iso, "source": source, "shoot_day": None}

    named = _FILENAME.search(filename or "")
    if named:
        iso = _iso(int(named.group(3)), int(named.group(2)), int(named.group(1)))
        if iso:
            return {"date": iso, "source": "filename", "shoot_day": None}

    return None
