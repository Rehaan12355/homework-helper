"""Decides what a student should work on next.

Each unfinished assignment gets a priority score from how soon it's due and
how many points it's worth. Overdue work comes first. Given an amount of free
time, the planner picks the highest-priority work that fits, and explains each
pick in a short sentence that sounds natural when spoken.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homework_helper.canvas import Assignment

# Rough time estimates by assignment type, checked in order against the
# title. First match wins. Bedrock can replace these with smarter estimates.
TIME_RULES = [
    (r"survey|check.?in|acknowledg", 5),
    (r"pre.?lab", 20),
    (r"pre.?lecture|pretest|reading", 20),
    (r"lab|write.?up|report", 90),
    (r"essay|paper|project", 120),
    (r"exam|midterm|final", 90),
    (r"quiz|test", 30),
    (r"\bhw\b|homework|problem set|assignment", 60),
    (r"discussion|reply|post", 30),
]
DEFAULT_MINUTES = 45

# Work overdue by more than this is probably closed for submission, so it
# drops to the bottom instead of crowding out work that still counts.
STALE_AFTER = timedelta(days=7)


@dataclass
class Pick:
    assignment: Assignment
    minutes: int
    score: float
    reason: str


def estimate_minutes(a: Assignment) -> int:
    title = a.title.lower()
    for pattern, minutes in TIME_RULES:
        if re.search(pattern, title):
            return minutes
    if a.kind == "quiz":
        return 30
    if a.kind == "discussion_topic":
        return 30
    return DEFAULT_MINUTES


def priority(a: Assignment, now: datetime) -> float:
    """Higher means do it sooner."""
    if a.locks is not None and a.locks < now:
        return 0.0                             # Canvas won't accept it anymore
    points = a.points if a.points else 1.0
    hours_left = (a.due - now).total_seconds() / 3600

    if hours_left < 0:
        days_late = -hours_left / 24
        if days_late > STALE_AFTER.days:
            return points * 0.01               # probably too late to count
        # Overdue work counts like something due right now, then fades: the
        # longer it's late, the more likely it's closed, heavily penalized,
        # or already done on a site Canvas can't see (like Pearson).
        return points / (1 + days_late / 2)

    # Urgency falls off as the deadline gets further away: something due in
    # 6 hours is about 4x as pressing as something due in 2 days.
    urgency = 12 / (hours_left + 12)
    return points * urgency


def when(due: datetime, now: datetime) -> str:
    """Says a due date the way a person would, e.g. 'tomorrow at 11:59 PM'."""
    local_due, local_now = due.astimezone(), now.astimezone()
    days = (local_due.date() - local_now.date()).days
    time = local_due.strftime("%I:%M %p").lstrip("0")
    if days < 0:
        return f"{-days} day{'s' if days != -1 else ''} ago"
    if days == 0:
        return f"today at {time}"
    if days == 1:
        return f"tomorrow at {time}"
    if days < 7:
        return f"{local_due:%A} at {time}"
    return f"{local_due:%B} {local_due.day}"


def explain(a: Assignment, now: datetime) -> str:
    points = f", worth {a.points:g} points" if a.points else ""
    if a.overdue:
        return (f"It was due {when(a.due, now)}{points}, and Canvas doesn't "
                "show it submitted.")
    return f"It's due {when(a.due, now)}{points}."


def ranked(work: list[Assignment], now: datetime | None = None) -> list[Pick]:
    """All unfinished work, most important first."""
    now = now or datetime.now(timezone.utc)
    picks = [Pick(a, estimate_minutes(a), priority(a, now), explain(a, now))
             for a in work if not a.done]
    picks = [p for p in picks if p.score > 0]  # drop locked work
    return sorted(picks, key=lambda p: (-p.score, p.assignment.due))


def what_to_work_on(work: list[Assignment], minutes_free: int | None = None,
                    now: datetime | None = None) -> list[Pick]:
    """The best work to do now. With `minutes_free`, picks the most important
    work that fits in that time; otherwise returns the single top pick."""
    order = ranked(work, now)
    if minutes_free is None:
        return order[:1]

    chosen, time_left = [], minutes_free
    for pick in order:
        if pick.score < 0.05:
            break                              # only stale work left
        if pick.minutes <= time_left:
            chosen.append(pick)
            time_left -= pick.minutes
    # If nothing fits, still suggest starting the most important thing.
    return chosen or order[:1]


if __name__ == "__main__":
    # Try it with your real Canvas work: python -m homework_helper.planner 120
    import sys
    from dotenv import load_dotenv
    from homework_helper.canvas import Canvas, CanvasError

    load_dotenv(".env")
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        work = Canvas.from_env().assignments()
    except CanvasError as err:
        sys.exit(str(err))

    print(f"With {minutes} minutes free:" if minutes else "Top priority:")
    for p in what_to_work_on(work, minutes):
        print(f"  ~{p.minutes:3} min  {p.assignment.title}. {p.reason}")

    print("\nFull ranking:")
    for p in ranked(work):
        print(f"  {p.score:6.2f}  ~{p.minutes:3} min  {p.assignment.title}")
