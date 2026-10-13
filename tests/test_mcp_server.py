import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from mcp import Client

from homework_helper import mcp_server
from homework_helper.canvas import Assignment

TZ = ZoneInfo("America/Los_Angeles")
# Saturday Oct 10, 2026 at 2:00 PM local time.
NOW = datetime(2026, 10, 10, 14, 0, tzinfo=TZ)
_ids = iter(range(1, 1000))


def work(title, due, points=10.0):
    return Assignment(id=next(_ids), course_id=1, course="Physics", title=title,
                      kind="assignment", due=due, points=points, url="",
                      submitted=False, missing=False, graded=False)


@pytest.fixture(autouse=True)
def fake_canvas(monkeypatch):
    monkeypatch.setenv("STUDENT_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setattr(mcp_server, "now", lambda: NOW)
    homework = [work("Quiz 2", NOW - timedelta(days=2), points=30),
                work("CH 03 HW", NOW + timedelta(hours=20)),
                work("Chapter 04 pre-lecture", NOW + timedelta(days=3)),
                work("STEM Fluency Assignment 3", NOW + timedelta(days=5)),
                work("STEM Fluency Assignment 4", NOW + timedelta(days=6))]
    homework[1].name = "Chapter 3 homework"
    monkeypatch.setattr(mcp_server, "load_work", lambda: homework)
    return homework


class FakeCanvas:
    def __init__(self):
        self.marked = []

    def mark_done(self, a, done=True):
        a.marked_done = done
        self.marked.append((a.title, done))


def call(tool, args=None):
    async def go():
        async with Client(mcp_server.server) as client:
            result = await client.call_tool(tool, args or {})
            assert not result.is_error, result.content
            return result.structured_content
    return asyncio.run(go())


def test_lists_the_homework_tools():
    async def go():
        async with Client(mcp_server.server) as client:
            return {t.name for t in (await client.list_tools()).tools}
    assert asyncio.run(go()) == {"what_should_i_work_on", "plan_my_week",
                                 "list_assignments", "check_reminders",
                                 "add_study_sessions", "mark_complete"}


def test_what_should_i_work_on():
    result = call("what_should_i_work_on")
    assert result["say"].startswith("Work on Quiz 2.")
    assert len(result["picks"]) == 1


def test_what_fits_in_an_hour():
    result = call("what_should_i_work_on", {"minutes_free": 60})
    assert result["say"].startswith("With an hour free, you can do Quiz 2 and")
    assert sum(p["minutes"] for p in result["picks"]) <= 60


def test_plan_my_week():
    result = call("plan_my_week")
    assert result["say"] == ("Start today at 4 PM with studying for Quiz 2. Today: Study for Quiz 2, "
                             "Quiz 2 and Chapter 3 homework. After that, 3 more sessions "
                             "through Tuesday. Some days run over your usual study time.")
    assert result["whole_week"].startswith("Today: Study for Quiz 2")
    assert len(result["days"]) == 7
    [study, quiz, homework] = result["days"][0]["sessions"]
    assert study["label"] == "Study for Quiz 2" and study["task"] == "study"
    assert study["start"].endswith("T16:00:00-07:00") and quiz["start"] > study["end"]
    assert result["fits_your_calendar"] is False


def test_check_reminders():
    result = call("check_reminders")
    assert "Chapter 3 homework is due tomorrow" in result["say"]
    assert "Quiz 2 was due 2 days ago" in result["say"]


def test_list_assignments():
    result = call("list_assignments")
    assert result["say"].startswith("You have 5 unfinished assignments.")
    assert result["assignments"][1]["name"] == "Chapter 3 homework"
    assert result["assignments"][1]["title"] == "CH 03 HW"


def test_add_study_sessions(monkeypatch):
    from homework_helper import study_sessions
    from tests.test_study_sessions import FakeCalendar
    calendar = FakeCalendar([])
    monkeypatch.setattr(study_sessions, "google_calendar", lambda: calendar)
    result = call("add_study_sessions")
    assert result["say"].startswith("I added 6 study sessions to your calendar. "
                                    "The first is Study for Quiz 2 at 4:00 PM.")
    assert len(calendar.events_by_id) == 6


def test_mark_complete(monkeypatch):
    canvas = FakeCanvas()
    monkeypatch.setattr(mcp_server, "canvas", lambda: canvas)
    result = call("mark_complete", {"assignment": "chapter three homework"})
    assert canvas.marked == [("CH 03 HW", True)]
    assert result["say"] == ("Done, I marked Chapter 3 homework as done in Canvas. "
                             "Next up is Quiz 2.")


def test_mark_complete_asks_when_unsure(monkeypatch):
    canvas = FakeCanvas()
    monkeypatch.setattr(mcp_server, "canvas", lambda: canvas)
    result = call("mark_complete", {"assignment": "stem fluency"})
    assert canvas.marked == []
    assert result["say"] == "Which one: STEM Fluency Assignment 3 or STEM Fluency Assignment 4?"


def test_mark_complete_can_undo(monkeypatch, fake_canvas):
    canvas = FakeCanvas()
    monkeypatch.setattr(mcp_server, "canvas", lambda: canvas)
    fake_canvas[0].marked_done = True
    result = call("mark_complete", {"assignment": "quiz 2", "done": False})
    assert canvas.marked == [("Quiz 2", False)]
    assert result["say"] == "Okay, Quiz 2 is back on your list."


def test_mark_complete_not_found(monkeypatch):
    monkeypatch.setattr(mcp_server, "canvas", lambda: pytest.fail("shouldn't change Canvas"))
    result = call("mark_complete", {"assignment": "history essay"})
    assert result["say"] == "I couldn't find an assignment called history essay."


def sessions_on(result, day=0):
    return [(s["start"][11:16], s["end"][11:16], s["label"]) for s in result["days"][day]["sessions"]]


def test_plan_works_around_a_busy_time():
    before = sessions_on(call("plan_my_week"))
    assert any(start < "17:00" < end for start, end, _ in before)    # something runs 4–5 PM
    result = call("plan_my_week", {"busy": [{"label": "Gym", "start": "16:00", "end": "17:00"}]})
    assert result["say"].startswith("Got it: Gym from 4 to 5 PM today. Here's the new plan. "
                                    "Start today at 5 PM with")
    assert all(start >= "17:00" for start, _, _ in sessions_on(result))
    assert result["days"][0]["busy"] == [{"label": "Gym", "start": "2026-10-10T16:00:00-07:00",
                                          "end": "2026-10-10T17:00:00-07:00"}]


def test_plan_changes_are_remembered_until_removed():
    call("plan_my_week", {"busy": [{"label": "Gym", "start": "16:00", "end": "17:00",
                                    "days": "every day"}], "bedtime": "21:00"})
    again = call("plan_my_week")
    assert not again["say"].startswith("Got it")
    assert all(s >= "17:00" and e <= "21:00" for d in range(7)
               for s, e, _ in sessions_on(again, d))
    assert again["study_hours"] == {"start": "4 PM", "bedtime": "9 PM"}
    removed = call("plan_my_week", {"remove": ["gym"]})
    assert removed["say"].startswith("Got it: I took out gym.")
    assert removed["days"][1]["busy"] == []


def test_plan_explains_changes_it_cannot_understand():
    result = call("plan_my_week", {"bedtime": "after the movie"})
    assert result["say"] == "I didn't understand the time after the movie. Could you say it another way?"


def test_calendar_sessions_use_the_same_changes(monkeypatch):
    from homework_helper import study_sessions
    from tests.test_study_sessions import FakeCalendar
    calendar = FakeCalendar([])
    monkeypatch.setattr(study_sessions, "google_calendar", lambda: calendar)
    call("plan_my_week", {"busy": [{"label": "Gym", "start": "16:00", "end": "17:00"}]})
    call("add_study_sessions")
    today = [e for e in calendar.events_by_id.values()
             if e["start"]["dateTime"].startswith("2026-10-10")]
    assert today and all(e["start"]["dateTime"][11:16] >= "17:00" for e in today)
