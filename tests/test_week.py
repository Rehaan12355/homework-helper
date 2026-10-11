from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homework_helper.canvas import Assignment
from homework_helper.week import last_work_day, plan_week, spoken_summary

TZ = ZoneInfo("America/Los_Angeles")
# Saturday Oct 10, 2026 at 2:00 PM local time.
NOW = datetime(2026, 10, 10, 14, 0, tzinfo=TZ)
_ids = iter(range(1, 1000))


@pytest.fixture(autouse=True)
def student_timezone(monkeypatch):
    monkeypatch.setenv("STUDENT_TIMEZONE", "America/Los_Angeles")


def work(title, due, points=10.0, done=False):
    return Assignment(id=next(_ids), course_id=1, course="Physics", title=title,
                      kind="assignment", due=due, points=points, url="",
                      submitted=done, missing=False, graded=False)


def local(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def day_of(week, title):
    return next(d.date for d in week for p in d.picks if p.assignment.title == title)


def test_morning_deadlines_must_be_done_the_day_before():
    assert last_work_day(work("Lab", local(12, 10, 30))) == date(2026, 10, 11)
    assert last_work_day(work("HW", local(12, 23, 59))) == date(2026, 10, 12)


def test_every_assignment_is_planned_before_its_deadline():
    tasks = [work(f"Task {i}", local(11 + i % 5, 23, 59)) for i in range(10)]
    week = plan_week(tasks, NOW)
    for d in week:
        for p in d.picks:
            assert d.date <= last_work_day(p.assignment)
    assert sum(len(d.picks) for d in week) == 10


def test_spreads_work_instead_of_piling_on_today():
    # Three 60-minute homeworks all due Friday: shouldn't all land on one day.
    tasks = [work(f"CH 0{i} HW", local(16, 23, 59)) for i in range(3)]
    week = plan_week(tasks, NOW)
    assert len({day_of(week, t.title) for t in tasks}) == 3


def test_overdue_work_goes_on_today():
    week = plan_week([work("Quiz 2", local(8, 12), points=30)], NOW)
    assert day_of(week, "Quiz 2") == date(2026, 10, 10)


def test_finished_stale_and_far_future_work_is_left_out():
    week = plan_week([
        work("Done", local(13, 23, 59), done=True),
        work("Overdue last month", NOW - timedelta(days=30)),
        work("Due in three weeks", NOW + timedelta(days=21)),
    ], NOW)
    assert all(not d.picks for d in week)
    assert spoken_summary(week) == "You're all caught up for the week."


def test_todays_budget_is_only_the_time_left_before_bedtime():
    week = plan_week([], datetime(2026, 10, 10, 22, 0, tzinfo=TZ))
    assert week[0].budget == 60
    assert week[1].budget == 120


def test_flags_days_that_cannot_fit_everything():
    # Four 90-minute lab write-ups due tomorrow morning: only today is possible.
    tasks = [work(f"Lab write-up {i}", local(11, 9)) for i in range(4)]
    week = plan_week(tasks, NOW)
    assert week[0].over_budget
    assert "over your usual study time" in spoken_summary(week)


def test_spoken_summary_names_days():
    week = plan_week([work("Quiz 2", local(8, 12)),
                      work("CH 03 HW", local(12, 23, 59))], NOW)
    summary = spoken_summary(week)
    assert summary.startswith("Today: Quiz 2")
    assert "CH 03 HW" in summary and "minutes" in summary
