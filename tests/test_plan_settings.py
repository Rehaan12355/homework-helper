from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from homework_helper import plan_settings
from homework_helper.plan_settings import (Settings, SettingsError, change, parse_clock,
                                           resolve_days)

TZ = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 12)      # a Monday


def test_parses_spoken_and_24_hour_times():
    assert parse_clock("19:00") == time(19)
    assert parse_clock("7pm") == time(19)
    assert parse_clock("7:30 PM") == time(19, 30)
    assert parse_clock("12 am") == time(0)
    assert parse_clock("noon") == time(12)
    with pytest.raises(SettingsError):
        parse_clock("after dinner")


def test_days_become_dates_or_repeating_rules():
    assert resolve_days("today", TODAY) == "2026-10-12"
    assert resolve_days("tomorrow", TODAY) == "2026-10-13"
    assert resolve_days("Wednesday", TODAY) == "2026-10-14"
    assert resolve_days("monday", TODAY) == "2026-10-12"          # today counts
    assert resolve_days("every day", TODAY) == "every day"
    assert resolve_days("weekdays", TODAY) == "weekdays"
    assert resolve_days("Mondays", TODAY) == "every monday"
    assert resolve_days("every Friday", TODAY) == "every friday"
    with pytest.raises(SettingsError):
        resolve_days("someday", TODAY)


def test_changes_are_described_for_speaking():
    s = Settings()
    notes = change(s, TODAY, busy=[{"label": "Gym", "start": "19:00", "end": "20:00"}],
                   bedtime="22:00")
    assert notes == ["Gym from 7 to 8 PM today", "bedtime at 10 PM"]


def test_saying_it_again_replaces_the_old_time():
    s = Settings()
    change(s, TODAY, busy=[{"label": "Gym", "start": "19:00", "end": "20:00"}])
    change(s, TODAY, busy=[{"label": "gym", "start": "18:00", "end": "19:00"}])
    assert [(b.start, b.end) for b in s.busy] == [(time(18), time(19))]


def test_remove_by_label_or_everything():
    s = Settings()
    change(s, TODAY, busy=[{"label": "Gym", "start": "19:00", "end": "20:00", "days": "weekdays"},
                           {"label": "Dinner", "start": "18:00", "end": "18:30", "days": "every day"}],
           bedtime="22:00")
    assert change(s, TODAY, remove=["gym"]) == ["I took out gym"]
    assert [b.label for b in s.busy] == ["Dinner"]
    change(s, TODAY, remove=["all"])
    assert s.busy == [] and s.bedtime is None


def test_busy_times_land_on_the_right_days():
    s = Settings()
    change(s, TODAY, busy=[{"label": "Gym", "start": "19:00", "end": "20:00", "days": "weekdays"},
                           {"label": "Party", "start": "20:00", "end": "1:00", "days": "saturday"}])
    days = [date(2026, 10, 12 + i) for i in range(7)]
    found = s.busy_times(days, TZ)
    assert [(a.date().day, label) for a, _, label in found] == [
        (12, "Gym"), (13, "Gym"), (14, "Gym"), (15, "Gym"), (16, "Gym"), (17, "Party")]
    party = found[-1]
    assert party[1] == datetime(2026, 10, 18, 1, 0, tzinfo=TZ)      # past midnight


def test_saved_settings_forget_days_that_have_passed(saved_settings):
    s = Settings()
    change(s, TODAY, busy=[{"label": "Gym", "start": "19:00", "end": "20:00"},
                           {"label": "Dinner", "start": "18:00", "end": "18:30", "days": "every day"}],
           bedtime="22:30")
    plan_settings.save(s)
    later = plan_settings.load(date(2026, 10, 13))
    assert [b.label for b in later.busy] == ["Dinner"]
    assert later.bedtime == time(22, 30)
