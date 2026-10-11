"""The student's local time zone.

On a laptop this is the computer's time zone. In the cloud (AWS Lambda) the
server runs on UTC, so set STUDENT_TIMEZONE (e.g. "America/Los_Angeles") or
"due tonight at 11:59 PM" would be said in the wrong time zone.
"""

import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo


def local_tz() -> tzinfo | None:
    name = os.environ.get("STUDENT_TIMEZONE")
    return ZoneInfo(name) if name else None


def to_local(dt: datetime) -> datetime:
    """Converts to the student's time zone (the computer's, if unset)."""
    return dt.astimezone(local_tz())
