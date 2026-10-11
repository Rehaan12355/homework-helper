"""Proactive reminders for work that's due soon and not submitted.

Each assignment can get up to three reminders: the day before ("due
tomorrow"), a few hours before ("due in 3 hours"), and once if it goes
overdue. Reminders already sent are remembered, so checking twice a day
never repeats one. If a teacher moves the due date, reminders start over.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homework_helper.canvas import Assignment
from homework_helper.planner import estimate_minutes, is_stale, when

DAY_BEFORE = timedelta(hours=24)
HOURS_BEFORE = timedelta(hours=3)
FORGET_AFTER = timedelta(days=30)      # old reminder records get cleaned up


@dataclass
class Reminder:
    assignment: Assignment
    stage: str                         # "day", "soon", or "overdue"
    text: str

    @property
    def key(self) -> str:
        a = self.assignment
        return f"{a.id}:{a.due.isoformat()}:{self.stage}"


def spoken_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"about {minutes} minutes"
    if minutes == 60:
        return "about an hour"
    hours = minutes / 60
    return f"about {hours:g} hours" if hours == int(hours) else f"about {hours:.1f} hours"


def stage(a: Assignment, now: datetime) -> str | None:
    """Which reminder this assignment is due for, if any."""
    if a.done or a.locked or is_stale(a, now):
        return None
    left = a.due - now
    if left < timedelta(0):
        return "overdue"
    if left <= HOURS_BEFORE:
        return "soon"
    if left <= DAY_BEFORE:
        return "day"
    return None


def reminder_text(a: Assignment, stage: str, now: datetime) -> str:
    due = when(a.due, now)
    if stage == "overdue":
        return (f"{a.title} was due {due}, and Canvas doesn't show it submitted. "
                "It may still be worth turning in.")
    if stage == "soon":
        hours = (a.due - now).total_seconds() / 3600
        left = "under an hour" if hours < 1 else f"about {round(hours)} hours"
        return f"Heads up: {a.title} is due in {left} and isn't submitted yet."
    return (f"Reminder: {a.title} is due {due} and isn't submitted yet. "
            f"It takes {spoken_minutes(estimate_minutes(a))}.")


def due_reminders(work: list[Assignment], now: datetime | None = None) -> list[Reminder]:
    """Every reminder that applies right now, most urgent first."""
    now = now or datetime.now(timezone.utc)
    found = []
    for a in work:
        s = stage(a, now)
        if s:
            found.append(Reminder(a, s, reminder_text(a, s, now)))
    order = {"soon": 0, "day": 1, "overdue": 2}
    return sorted(found, key=lambda r: (order[r.stage], r.assignment.due))


class SentLog:
    """Remembers which reminders were sent, in a local JSON file.
    (In the cloud this is replaced by a DynamoDB table.)"""

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("REMINDER_LOG", "reminders_sent.json")
        try:
            with open(self.path) as f:
                self.sent = json.load(f)
        except FileNotFoundError:
            self.sent = {}

    def __contains__(self, key: str) -> bool:
        return key in self.sent

    def mark(self, keys: list[str], now: datetime) -> None:
        for key in keys:
            self.sent[key] = now.isoformat()
        cutoff = now - FORGET_AFTER
        self.sent = {k: t for k, t in self.sent.items()
                     if datetime.fromisoformat(t) > cutoff}
        with open(self.path, "w") as f:
            json.dump(self.sent, f, indent=1)


def check(work: list[Assignment], log: SentLog, now: datetime | None = None) -> list[Reminder]:
    """New reminders to send now. Marks them as sent."""
    now = now or datetime.now(timezone.utc)
    new = [r for r in due_reminders(work, now) if r.key not in log]
    if new:
        log.mark([r.key for r in new], now)
    return new


if __name__ == "__main__":
    # Check for reminders: python -m homework_helper.reminders [--all]
    # --all shows every reminder that applies, even ones already sent.
    import sys
    from dotenv import load_dotenv
    from homework_helper.canvas import Canvas, CanvasError

    load_dotenv(".env")
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    try:
        work = Canvas.from_env().assignments()
    except CanvasError as err:
        sys.exit(str(err))

    reminders = due_reminders(work) if "--all" in sys.argv else check(work, SentLog())
    if not reminders:
        print("No new reminders.")
    for r in reminders:
        print(f"  [{r.stage}] {r.text}")
