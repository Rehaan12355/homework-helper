from datetime import datetime, timedelta, timezone

from homework_helper.canvas import Assignment
from homework_helper.planner import (estimate_minutes, ranked, what_to_work_on,
                                     when)

NOW = datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc)
_next_id = iter(range(1, 1000))


def work(title, due_in_hours, points=10.0, done=False, kind="assignment",
         locks_in_hours=None):
    return Assignment(
        id=next(_next_id), course_id=1, course="Physics", title=title, kind=kind,
        due=NOW + timedelta(hours=due_in_hours), points=points,
        url="", submitted=done, missing=False, graded=False,
        locks=None if locks_in_hours is None else NOW + timedelta(hours=locks_in_hours))


def test_estimates_by_title():
    assert estimate_minutes(work("Chapter 04 pre-lecture", 1)) == 20
    assert estimate_minutes(work("Pre-lab for Free Fall", 1)) == 20
    assert estimate_minutes(work("Motion Lab Informal Lab write-up", 1)) == 90
    assert estimate_minutes(work("CH 03 HW", 1)) == 60
    assert estimate_minutes(work("Quiz 2", 1)) == 30
    assert estimate_minutes(work("First Day Survey", 1)) == 5
    assert estimate_minutes(work("Measuring pi wrap-up", 1)) == 45   # default


def test_sooner_deadline_ranks_higher_at_equal_points():
    order = ranked([work("Later", 72), work("Sooner", 6)], NOW)
    assert [p.assignment.title for p in order] == ["Sooner", "Later"]


def test_big_assignment_can_beat_a_slightly_sooner_small_one():
    order = ranked([work("Tiny", 20, points=2), work("Big quiz", 30, points=30)], NOW)
    assert order[0].assignment.title == "Big quiz"


def test_overdue_ranks_high_but_fades_and_stale_goes_last():
    order = ranked([
        work("Due in 3 days", 72),
        work("Overdue yesterday", -24),
        work("Overdue last month", -24 * 30),
    ], NOW)
    assert [p.assignment.title for p in order] == [
        "Overdue yesterday", "Due in 3 days", "Overdue last month"]


def test_small_overdue_item_does_not_beat_big_upcoming_quiz():
    # Real case: a 5-point item 5 days late was outranking a 30-point quiz.
    order = ranked([work("Old 5-pointer", -24 * 5, points=5),
                    work("Quiz", 80, points=30)], NOW)
    assert order[0].assignment.title == "Quiz"


def test_locked_work_is_never_suggested():
    order = ranked([work("Locked", -2, locks_in_hours=-1),
                    work("Still open", -2, locks_in_hours=24)], NOW)
    assert [p.assignment.title for p in order] == ["Still open"]


def test_finished_work_is_never_suggested():
    assert ranked([work("Done", 5, done=True)], NOW) == []


def test_fits_work_into_free_time():
    picks = what_to_work_on([
        work("Lab write-up", 10),            # 90 min
        work("Chapter 4 pre-lecture", 12),   # 20 min
        work("CH 03 HW", 30),                # 60 min
    ], minutes_free=120, now=NOW)
    titles = [p.assignment.title for p in picks]
    assert sum(p.minutes for p in picks) <= 120
    assert titles[0] == "Lab write-up"
    assert "Chapter 4 pre-lecture" in titles and "CH 03 HW" not in titles


def test_suggests_starting_something_when_nothing_fits():
    picks = what_to_work_on([work("Lab write-up", 10)], minutes_free=15, now=NOW)
    assert [p.assignment.title for p in picks] == ["Lab write-up"]


def test_no_time_given_returns_single_top_pick():
    picks = what_to_work_on([work("A", 50), work("B", 5)], now=NOW)
    assert len(picks) == 1 and picks[0].assignment.title == "B"


def test_spoken_due_dates():
    now = datetime(2026, 10, 10, 12, 0).astimezone()   # local noon
    assert when(now.replace(hour=23, minute=59), now) == "today at 11:59 PM"
    assert when(now + timedelta(days=1), now) == "tomorrow at 12:00 PM"
    assert when(now - timedelta(days=2), now) == "2 days ago"
    assert when(now - timedelta(days=1), now) == "1 day ago"


def test_reason_mentions_points_and_overdue():
    [pick] = ranked([work("Quiz 2", -30, points=30)], NOW)
    assert "30 points" in pick.reason and "doesn't show it submitted" in pick.reason


def test_stale_work_with_many_points_is_not_suggested():
    # A 50-point item a month overdue must not fill free time.
    picks = what_to_work_on([work("Old project", -24 * 30, points=50),
                             work("CH 03 HW", 30)], minutes_free=120, now=NOW)
    assert [p.assignment.title for p in picks] == ["CH 03 HW"]
