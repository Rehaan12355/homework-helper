from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homework_helper.canvas import Assignment
from homework_helper.planner import Pick
from homework_helper.study_sessions import (TAG, busy_times, event_body,
                                            schedule, sync)
from homework_helper.week import Day

TZ = ZoneInfo("America/Los_Angeles")
# Saturday Oct 10, 2026 at 2:00 PM local time.
NOW = datetime(2026, 10, 10, 14, 0, tzinfo=TZ)
_ids = iter(range(1, 1000))


@pytest.fixture(autouse=True)
def student_settings(monkeypatch):
    monkeypatch.setenv("STUDENT_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("STUDY_START", "16:00")


def pick(title, minutes):
    a = Assignment(id=next(_ids), course_id=1, course="Physics", title=title,
                   kind="assignment", due=NOW + timedelta(days=3), points=10.0,
                   url="https://canvas.example/a", submitted=False, missing=False,
                   graded=False)
    return Pick(a, minutes, 1.0, "It's due Tuesday.")


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def event(start, end, ours=False, **extra):
    e = {"id": f"e{next(_ids)}", "start": {"dateTime": start.isoformat()},
         "end": {"dateTime": end.isoformat()}, **extra}
    if ours:
        e["extendedProperties"] = {"private": {TAG: "1"}}
    return e


def test_sessions_start_at_study_time_with_breaks():
    week = [Day(date(2026, 10, 11), 120, [pick("Quiz", 30), pick("HW", 60)])]
    sessions, unplaced = schedule(week, [], NOW)
    assert [(s.start, s.end) for s in sessions] == [
        (at(11, 16), at(11, 16, 30)), (at(11, 16, 40), at(11, 17, 40))]
    assert unplaced == []


def test_today_starts_now_not_in_the_past():
    later = at(10, 17, 2)
    week = [Day(date(2026, 10, 10), 120, [pick("Quiz", 30)])]
    sessions, _ = schedule(week, [], later)
    assert sessions[0].start == at(10, 17, 5)       # next 5-minute mark


def test_works_around_existing_events():
    practice = (at(11, 16), at(11, 18))
    week = [Day(date(2026, 10, 11), 120, [pick("Quiz", 30)])]
    sessions, _ = schedule(week, [practice], NOW)
    assert sessions[0].start == at(11, 18)


def test_work_that_does_not_fit_before_bedtime_is_reported():
    late = at(10, 22, 30)
    week = [Day(date(2026, 10, 10), 30, [pick("Lab write-up", 90)])]
    sessions, unplaced = schedule(week, [], late)
    assert sessions == [] and unplaced[0].assignment.title == "Lab write-up"


def test_what_counts_as_busy():
    events = [
        event(at(11, 16), at(11, 17)),                               # busy
        event(at(11, 18), at(11, 19), transparency="transparent"),   # marked free
        event(at(11, 19), at(11, 20),
              attendees=[{"self": True, "responseStatus": "declined"}]),
        {"start": {"date": "2026-10-11"}, "end": {"date": "2026-10-12"}},  # all day
        event(at(11, 20), at(11, 21), ours=True),                    # gets replaced
        event(at(10, 13, 30), at(10, 14, 30), ours=True),            # in progress
    ]
    assert busy_times(events, NOW) == [(at(10, 13, 30), at(10, 14, 30)),
                                       (at(11, 16), at(11, 17))]


def test_event_is_tagged_and_links_to_canvas():
    week = [Day(date(2026, 10, 11), 120, [pick("CH 03 HW", 60)])]
    body = event_body(schedule(week, [], NOW)[0][0])
    assert body["summary"] == "Study: CH 03 HW"
    assert "https://canvas.example/a" in body["description"]
    assert body["extendedProperties"]["private"][TAG] == "1"
    assert body["start"]["timeZone"] == "America/Los_Angeles"


class FakeCalendar:
    """Stands in for the Google Calendar API."""

    def __init__(self, events):
        self.events_by_id = {e["id"]: e for e in events}

    def events(self):
        return self

    def list(self, **kwargs):
        return Run({"items": list(self.events_by_id.values())})

    def delete(self, calendarId, eventId):
        return Run(None, lambda: self.events_by_id.pop(eventId))

    def insert(self, calendarId, body):
        new = {"id": f"new{next(_ids)}", **body}
        return Run(new, lambda: self.events_by_id.update({new["id"]: new}))


class Run:
    def __init__(self, result, action=None):
        self.result, self.action = result, action

    def execute(self):
        if self.action:
            self.action()
        return self.result


def test_resync_replaces_old_sessions_and_keeps_the_students_events():
    practice = event(at(11, 16), at(11, 18), summary="Soccer practice")
    old_session = event(at(11, 20), at(11, 21), ours=True, summary="Study: old")
    calendar = FakeCalendar([practice, old_session])
    week = [Day(date(2026, 10, 10), 0, []),
            Day(date(2026, 10, 11), 120, [pick("Quiz", 30)])]

    sync(calendar, week, NOW)
    sync(calendar, week, NOW)                      # running twice is safe

    summaries = sorted(e["summary"] for e in calendar.events_by_id.values())
    assert summaries == ["Soccer practice", "Study: Quiz"]
