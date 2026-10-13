from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from homework_helper.canvas import Assignment
from homework_helper.reminders import SentLog, check, due_reminders, spoken_minutes, stage

TZ = ZoneInfo("America/Los_Angeles")
# Saturday Oct 10, 2026 at 2:00 PM local time.
NOW = datetime(2026, 10, 10, 14, 0, tzinfo=TZ)
_ids = iter(range(1, 1000))


@pytest.fixture(autouse=True)
def student_timezone(monkeypatch):
    monkeypatch.setenv("STUDENT_TIMEZONE", "America/Los_Angeles")


def work(title, due, done=False, locks=None):
    return Assignment(id=next(_ids), course_id=1, course="Physics", title=title,
                      kind="assignment", due=due, points=10.0, url="",
                      submitted=done, missing=False, graded=False, locks=locks)


def test_stages():
    assert stage(work("HW", NOW + timedelta(hours=2)), NOW) == "soon"
    assert stage(work("HW", NOW + timedelta(hours=20)), NOW) == "day"
    assert stage(work("HW", NOW + timedelta(days=3)), NOW) is None
    assert stage(work("HW", NOW - timedelta(days=1)), NOW) == "overdue"


def test_no_reminders_for_finished_locked_or_long_overdue_work():
    assert stage(work("HW", NOW + timedelta(hours=2), done=True), NOW) is None
    assert stage(work("HW", NOW - timedelta(hours=2), locks=NOW - timedelta(hours=1)), NOW) is None
    assert stage(work("HW", NOW - timedelta(days=30)), NOW) is None


def test_reminder_wording():
    soon, day, late = due_reminders([
        work("Quiz 2", NOW - timedelta(days=2)),
        work("CH 03 HW", datetime(2026, 10, 11, 9, 0, tzinfo=TZ)),
        work("Pre-lab", NOW + timedelta(hours=2, minutes=50)),
    ], NOW)
    assert soon.text == "Heads up: Pre-lab is due in about 3 hours and isn't submitted yet."
    assert day.text == ("Reminder: CH 03 HW is due tomorrow at 9:00 AM and isn't "
                        "submitted yet.")
    assert late.text.startswith("Quiz 2 was due 2 days ago")


def test_spoken_minutes():
    assert spoken_minutes(30) == "about 30 minutes"
    assert spoken_minutes(60) == "about an hour"
    assert spoken_minutes(90) == "about 1.5 hours"
    assert spoken_minutes(120) == "about 2 hours"


def test_each_reminder_is_sent_only_once(tmp_path):
    hw = work("CH 03 HW", NOW + timedelta(hours=20))
    log = SentLog(str(tmp_path / "sent.json"))
    assert len(check([hw], log, NOW)) == 1
    assert check([hw], log, NOW + timedelta(hours=1)) == []
    # Remembered across runs (the log is saved to disk).
    assert check([hw], SentLog(str(tmp_path / "sent.json")), NOW) == []
    # Closer to the deadline it moves to the next stage and reminds again.
    assert [r.stage for r in check([hw], log, NOW + timedelta(hours=18))] == ["soon"]


def test_moved_due_date_starts_reminders_over(tmp_path):
    log = SentLog(str(tmp_path / "sent.json"))
    hw = work("CH 03 HW", NOW + timedelta(hours=20))
    check([hw], log, NOW)
    hw.due = NOW + timedelta(hours=22)                 # teacher moved it
    assert len(check([hw], log, NOW)) == 1
