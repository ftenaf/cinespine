"""
How long after wrap a department's paperwork arrived.

REQ-10 asks for this as a department sync matrix. It could not be computed for
most of this project's life: wrap is stated as a time of day -- `18:55` -- and
nothing bound a shoot day to a calendar date, so there was no moment to
subtract from. The date is now on the spine, and the subtraction is real.

# The measurement, and whether it means anything

Two different facts, and keeping them apart is the whole design.

The lag is always computable once the date is known: wrap on 2026-07-28 at
18:55 to the moment the document reached this system. That number is correct.

Whether it describes a *handover* is a separate question. Paperwork loaded into
the system months after the shoot is a backfill -- somebody importing history --
and its lag says nothing about how quickly sound filed on the night. Reporting
33 days as a sync lag in a matrix a reader expects to be hours does not tell
them a department is slow. It tells them something false in a form that looks
true, which is worse than the empty gauge this replaces.

So every measurement carries which kind it is, and nothing in this module
decides that a backfill is uninteresting -- only that it is not the same
measurement. A dashboard can show both; it cannot show them as one number.

# The window is a judgement, and is written down as one

`CINESPINE_HANDOVER_WINDOW_HOURS` decides where a handover stops being one.
The default of 48 hours is not a domain fact: it is the observation that a
day's paperwork is expected before the next shooting day begins, and that a
weekend can sit in between. It is configurable because a production that works
differently should not have this one's habits baked in.
"""
import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HANDOVER_WINDOW_HOURS = 48.0

HANDOVER = "handover"
BACKFILL = "backfill"


def handover_window_hours() -> float:
    """After how long a filing stops describing a handover."""
    raw = os.environ.get("CINESPINE_HANDOVER_WINDOW_HOURS", "").strip()
    if not raw:
        return DEFAULT_HANDOVER_WINDOW_HOURS
    try:
        hours = float(raw)
    except ValueError:
        logger.warning(
            "CINESPINE_HANDOVER_WINDOW_HOURS=%r is not a number; using %s",
            raw, DEFAULT_HANDOVER_WINDOW_HOURS,
        )
        return DEFAULT_HANDOVER_WINDOW_HOURS
    return hours if hours > 0 else DEFAULT_HANDOVER_WINDOW_HOURS


def wrap_moment(shoot_date: Optional[str], wrap_time: Optional[str]) -> Optional[datetime]:
    """
    The moment the day wrapped, or None.

    Needs both halves. A date with no wrap time and a wrap time with no date
    are each half a fact, and completing either by assuming the other would
    invent the baseline every number here is measured from.

    A wrap after midnight belongs to the night of the shoot day, not to the
    next morning: `02:30` on a day that called at 08:00 is the small hours of
    the following date. Treated that way rather than as a wrap sixteen hours
    before the call.
    """
    if not shoot_date or not wrap_time:
        return None

    try:
        date = datetime.strptime(str(shoot_date).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    parts = str(wrap_time).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    moment = datetime.combine(date, time(hour, minute), tzinfo=timezone.utc)
    # A shoot that wraps in the small hours wrapped on the night of this day.
    if hour < 6:
        moment += timedelta(days=1)
    return moment


def lag_seconds(wrapped_at: Optional[datetime], filed_at: Optional[datetime]) -> Optional[float]:
    """
    Seconds between wrap and the paperwork arriving, or None.

    Negative lags are kept, not clamped. Paperwork filed before wrap is a real
    thing -- a camera report closed at lunch, a call sheet filed in advance --
    and flattening it to zero would hide it. What it is not is a fast handover.
    """
    if wrapped_at is None or filed_at is None:
        return None
    if filed_at.tzinfo is None:
        filed_at = filed_at.replace(tzinfo=timezone.utc)
    return (filed_at - wrapped_at).total_seconds()


def classify(seconds: Optional[float]) -> Optional[str]:
    """
    Whether this measures a handover or a backfill.

    None where there is nothing to classify. A backfill is not a slow
    department: it is history being loaded, and calling it a lag would put a
    number in a sync matrix that means something else entirely.
    """
    if seconds is None:
        return None
    return HANDOVER if seconds <= handover_window_hours() * 3600 else BACKFILL
