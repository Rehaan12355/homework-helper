from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homework_helper.canvas import Assignment
from homework_helper.week import last_work_day, plan_week, sessions_for, spoken_summary

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


def sessions(week, title):
    """(date, label) of each session for one assignment, in plan order."""
    return [(d.date, p.label()) for d in week for p in d.picks if p.assignment.title == title]


def test_deadlines_before_study_time_must_be_done_the_day_before():
    assert last_work_day(work("Lab", local(12, 10, 30))) == date(2026, 10, 11)
    assert last_work_day(work("Mini-lab", local(12, 12, 30))) == date(2026, 10, 11)
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
    assert summary.startswith("Today: Study for Quiz 2 and Quiz 2.")
    assert "CH 03 HW" in summary and "minutes" not in summary


def test_quizzes_get_study_time_the_day_before():
    # Quiz due Tuesday night: study Monday, take it Monday or Tuesday.
    week = plan_week([work("Quiz 2: MCQ", local(13, 23, 59), points=30)], NOW)
    (study_day, study), (quiz_day, quiz) = sessions(week, "Quiz 2: MCQ")
    assert (study_day, study) == (date(2026, 10, 12), "Study for Quiz 2: MCQ")
    assert quiz == "Quiz 2: MCQ" and study_day <= quiz_day <= date(2026, 10, 13)


def test_exams_get_two_study_sessions_on_different_days():
    week = plan_week([work("Midterm exam", local(15, 9), points=100)], NOW)
    found = sessions(week, "Midterm exam")
    assert [label for _, label in found] == [
        "Study for Midterm exam", "Study for Midterm exam", "Midterm exam"]
    assert found[0][0] < found[1][0] < date(2026, 10, 15)


def test_pretests_and_pre_lectures_are_not_studied_for():
    a = work("Tutorial 2 pretest - Acceleration", local(13, 23, 59))
    from homework_helper.planner import ranked
    assert [p.task for p in sessions_for(ranked([a], NOW)[0])] == ["do"]


def test_long_work_is_split_across_days():
    week = plan_week([work("Motion Lab write-up", local(15, 23, 59))], NOW)
    found = sessions(week, "Motion Lab write-up")
    assert [label for _, label in found] == [
        "Motion Lab write-up, part 1 of 2", "Motion Lab write-up, part 2 of 2"]
    assert found[0][0] < found[1][0]
    assert all(p.minutes == 45 for d in week for p in d.picks)


def test_parts_on_the_same_day_are_said_once():
    # Overdue, so both parts have to be today.
    week = plan_week([work("Motion Lab write-up", local(10, 10, 30))], NOW)
    assert len(week[0].picks) == 2
    assert spoken_summary(week) == "Today: Motion Lab write-up."


def test_free_time_leaves_out_busy_times_and_bedtime():
    from homework_helper.week import Hours
    from datetime import time
    hours = Hours(start=time(16), bedtime=time(22),
                  busy=[(local(12, 19), local(12, 20)), (local(12, 19, 30), local(12, 20, 30))])
    # 4 PM to 10 PM is 6 hours; the gym and an overlapping event take 1.5.
    assert hours.free_minutes(date(2026, 10, 12), NOW) == 270
    # Today it's already 2 PM, but study time hasn't started yet.
    assert hours.free_minutes(date(2026, 10, 10), NOW) == 360


def test_bedtime_after_midnight_counts_into_the_night():
    from homework_helper.week import Hours
    from datetime import time
    assert Hours(start=time(16), bedtime=time(1)).free_minutes(date(2026, 10, 12), NOW) == 540


def test_a_full_evening_shrinks_that_days_budget():
    from homework_helper.week import Hours
    from datetime import time
    # Busy all Monday evening but 30 minutes: only short work goes there.
    hours = Hours(start=time(16), bedtime=time(22), busy=[(local(12, 16, 30), local(12, 22))])
    week = plan_week([], NOW, hours=hours)
    assert next(d for d in week if d.date == date(2026, 10, 12)).budget == 30
