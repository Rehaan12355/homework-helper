"""The student's own changes to their study plan, remembered between plans.

"Squeeze in my gym time from 7 to 8", "I'm going to bed at 10", "I get home
at 5": each becomes a setting the week plan works around. One-off times
("today", "Wednesday") are saved with their date and dropped once it has
passed; repeating ones ("every day", "weekdays", "every Monday") stay until
the student removes them.

Kept in DynamoDB when HOMEWORK_TABLE is set (in the cloud), otherwise in a
local JSON file, the same way as names.py.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
REPEATING = {"every day": range(7), "daily": range(7), "weekdays": range(5),
             "weekends": range(5, 7)}


class SettingsError(ValueError):
    """A change that can't be understood, with a message safe to speak."""


@dataclass
class BusyTime:
    label: str
    start: time
    end: time
    days: str            # an ISO date, or "every day", "weekdays", "weekends", "every monday"

    def on(self, day: date) -> bool:
        if self.days in REPEATING:
            return day.weekday() in REPEATING[self.days]
        if self.days.startswith("every "):
            return WEEKDAYS[day.weekday()] == self.days.removeprefix("every ")
        return self.days == day.isoformat()

    def to_json(self) -> dict:
        return {"label": self.label, "start": self.start.strftime("%H:%M"),
                "end": self.end.strftime("%H:%M"), "days": self.days}


@dataclass
class Settings:
    bedtime: time | None = None
    study_start: time | None = None
    busy: list[BusyTime] = field(default_factory=list)

    def busy_times(self, days: list[date], tz: tzinfo | None) -> list[tuple[datetime, datetime, str]]:
        """The student's busy times on these days, as (start, end, label)."""
        found = []
        for day in days:
            for b in self.busy:
                if b.on(day):
                    start = datetime.combine(day, b.start, tz)
                    end = datetime.combine(day, b.end, tz)
                    if end <= start:                 # runs past midnight
                        end += timedelta(days=1)
                    found.append((start, end, b.label))
        return sorted(found)

    def to_json(self) -> dict:
        return {"bedtime": self.bedtime and self.bedtime.strftime("%H:%M"),
                "study_start": self.study_start and self.study_start.strftime("%H:%M"),
                "busy": [b.to_json() for b in self.busy]}

    @classmethod
    def from_json(cls, data: dict, today: date) -> "Settings":
        busy = [BusyTime(b["label"], parse_clock(b["start"]), parse_clock(b["end"]), b["days"])
                for b in data.get("busy", [])]
        # One-off times that have passed are forgotten.
        busy = [b for b in busy if not _is_date(b.days) or b.days >= today.isoformat()]
        return cls(bedtime=data.get("bedtime") and parse_clock(data["bedtime"]),
                   study_start=data.get("study_start") and parse_clock(data["study_start"]),
                   busy=busy)


def _is_date(days: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", days))


def parse_clock(text: str) -> time:
    """"19:00", "7:30 PM", "7pm", "noon" -> a time."""
    t = text.strip().lower().replace(".", "")
    if t in ("noon", "midday"):
        return time(12)
    if t == "midnight":
        return time(0)
    m = re.fullmatch(r"([0-9]{1,2})(?::([0-9]{2}))?\s*(am|pm)?", t)
    if not m:
        raise SettingsError(f"I didn't understand the time {text}.")
    hour, minute, half = int(m[1]), int(m[2] or 0), m[3]
    if half == "pm" and hour != 12:
        hour += 12
    elif half == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise SettingsError(f"I didn't understand the time {text}.")
    return time(hour, minute)


def resolve_days(text: str, today: date) -> str:
    """What the student said ("today", "Wednesday", "every Monday",
    "weekdays") as it's saved: a date for one-off days, a rule otherwise."""
    t = re.sub(r"\s+", " ", (text or "today").strip().lower())
    t = {"everyday": "every day", "each day": "every day", "weeknights": "weekdays",
         "school days": "weekdays", "weekend": "weekends"}.get(t, t)
    if t in REPEATING:
        return t
    if t == "today" or t == "tonight":
        return today.isoformat()
    if t == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    plural = t.removesuffix("s")
    if t.startswith("every ") and t.removeprefix("every ").removesuffix("s") in WEEKDAYS:
        return "every " + t.removeprefix("every ").removesuffix("s")
    if plural in WEEKDAYS and t.endswith("s"):          # "mondays"
        return "every " + plural
    if t in WEEKDAYS:                                   # the next one, today included
        ahead = (WEEKDAYS.index(t) - today.weekday()) % 7
        return (today + timedelta(days=ahead)).isoformat()
    if _is_date(t):
        return t
    raise SettingsError(f"I didn't understand the day {text}.")


def change(settings: Settings, today: date, busy: list[dict] | None = None,
           bedtime: str | None = None, study_start: str | None = None,
           remove: list[str] | None = None) -> list[str]:
    """Applies the student's changes. Returns a short spoken note for each."""
    notes = []
    for label in remove or []:
        if label.strip().lower() in ("all", "everything"):
            settings.busy, settings.bedtime, settings.study_start = [], None, None
            notes.append("I cleared your changes")
            continue
        before = len(settings.busy)
        settings.busy = [b for b in settings.busy if b.label.lower() != label.strip().lower()]
        if label.strip().lower() == "bedtime":
            settings.bedtime = None
            notes.append("I reset your bedtime")
        elif label.strip().lower() in ("start time", "study start"):
            settings.study_start = None
            notes.append("I reset when you start studying")
        elif len(settings.busy) < before:
            notes.append(f"I took out {label.strip()}")
    for b in busy or []:
        new = BusyTime(label=(b.get("label") or "Busy").strip(), start=parse_clock(b["start"]),
                       end=parse_clock(b["end"]), days=resolve_days(b.get("days", "today"), today))
        if new.start == new.end:
            raise SettingsError(f"{new.label} needs an end time after its start.")
        # Saying it again replaces the old time for the same thing and days.
        settings.busy = [x for x in settings.busy
                         if not (x.label.lower() == new.label.lower() and x.days == new.days)]
        settings.busy.append(new)
        notes.append(f"{new.label} {spoken_span(new.start, new.end)} {spoken_days(new.days, today)}")
    if bedtime:
        settings.bedtime = parse_clock(bedtime)
        notes.append(f"bedtime at {spoken_clock(settings.bedtime)}")
    if study_start:
        settings.study_start = parse_clock(study_start)
        notes.append(f"studying from {spoken_clock(settings.study_start)}")
    return notes


def spoken_clock(t: time) -> str:
    if t == time(12):
        return "noon"
    if t == time(0):
        return "midnight"
    return datetime.combine(date.min, t).strftime("%I:%M %p" if t.minute else "%I %p").lstrip("0")


def spoken_span(start: time, end: time) -> str:
    a, b = spoken_clock(start), spoken_clock(end)
    if a[-2:] == b[-2:] and a[-2:] in ("AM", "PM"):     # "7 to 8 PM"
        a = a[:-3]
    return f"from {a} to {b}"


def spoken_days(days: str, today: date) -> str:
    if days in REPEATING:
        return "every day" if days == "daily" else days
    if days.startswith("every "):
        return f"every {days.removeprefix('every ').capitalize()}"
    d = date.fromisoformat(days)
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return f"on {d:%A}"


# --- Where settings are kept ------------------------------------------------

class FileSettings:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("PLAN_SETTINGS_FILE", "plan_settings.json")

    def load(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save(self, data: dict) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=1)


def default_store():
    if os.environ.get("HOMEWORK_TABLE"):
        from homework_helper import store
        return store.DynamoSettings(store.table())
    return FileSettings()


def load(today: date, saved=None) -> Settings:
    return Settings.from_json((saved or default_store()).load(), today)


def save(settings: Settings, saved=None) -> None:
    (saved or default_store()).save(settings.to_json())
