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
                work("Chapter 04 pre-lecture", NOW + timedelta(days=3))]
    monkeypatch.setattr(mcp_server, "load_work", lambda: homework)


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
                                 "add_study_sessions"}


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
    assert result["say"].startswith("Today: Quiz 2")
    assert len(result["days"]) == 7


def test_check_reminders():
    result = call("check_reminders")
    assert "CH 03 HW is due tomorrow" in result["say"]
    assert "Quiz 2 was due 2 days ago" in result["say"]


def test_list_assignments():
    result = call("list_assignments")
    assert result["say"].startswith("You have 3 unfinished assignments.")


def test_add_study_sessions(monkeypatch):
    from homework_helper import study_sessions
    from tests.test_study_sessions import FakeCalendar
    calendar = FakeCalendar([])
    monkeypatch.setattr(study_sessions, "google_calendar", lambda: calendar)
    result = call("add_study_sessions")
    assert result["say"].startswith("I added 3 study sessions to your calendar.")
    assert len(calendar.events_by_id) == 3
