"""Plans the student's week: which homework to do on which day.

Each assignment is placed on a day before it's due. Work is spread out
instead of piled onto today: the most urgent work is placed first, each on
the lightest day that still beats its deadline. Every day has a time budget,
and today only counts the time left before bedtime.

The plan leaves room to learn, not just to finish:
- Quizzes and tests get study time first, on an earlier day when there is
  one (the day before is best for remembering), and exams get two sessions.
- Long work (a lab report, an essay) is split into sessions of about an hour
  on separate days, since nobody focuses well for two hours straight.
"""

import math
import os
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta, timezone

from homework_helper.canvas import Assignment
from homework_helper.clock import to_local
from homework_helper.planner import Pick, is_stale, ranked

DAILY_MINUTES = 120
BEDTIME = time(23, 0)

# Whole words only, so a "pretest" isn't treated as a test.
QUIZ = re.compile(r"(?<![a-z])(quiz|test(?![a-z]))", re.I)
EXAM = re.compile(r"(?<![a-z])(exam|midterm|final(?![a-z]))", re.I)
QUIZ_STUDY_MINUTES = 45
EXAM_STUDY_MINUTES = 60
LONGEST_SESSION = 60          # longer work is split across days


@dataclass
class Day:
    date: date
    budget: int                              # minutes available
    picks: list[Pick] = field(default_factory=list)

    @property
    def planned(self) -> int:
        return sum(p.minutes for p in self.picks)

    @property
    def over_budget(self) -> bool:
        return self.planned > self.budget


def study_start() -> time:
    """When study time begins each day, from STUDY_START (e.g. "16:00")."""
    hours, minutes = os.environ.get("STUDY_START", "16:00").split(":")
    return time(int(hours), int(minutes))


def last_work_day(a: Assignment) -> date:
    """The last day this can realistically be worked on: work due before
    study time starts (a 10:30 AM lab, a 12:30 PM class) has to be done the
    day before."""
    due = to_local(a.due)
    return due.date() - timedelta(days=1) if due.time() <= study_start() else due.date()


def sessions_for(pick: Pick) -> list[Pick]:
    """The study sessions one assignment needs, in the order to do them."""
    title = pick.assignment.title
    if EXAM.search(title):
        studies = [EXAM_STUDY_MINUTES] * 2
    elif QUIZ.search(title):
        studies = [QUIZ_STUDY_MINUTES]
    else:
        studies = []
    plan = [replace(pick, minutes=m, task="study", part=i + 1, parts=len(studies))
            for i, m in enumerate(studies)]
    # A quiz or exam is taken in one sitting; other long work is split.
    split = pick.minutes > LONGEST_SESSION and not studies
    parts = math.ceil(pick.minutes / LONGEST_SESSION) if split else 1
    plan += [replace(pick, minutes=math.ceil(pick.minutes / parts), part=i + 1, parts=parts)
             for i in range(parts)]
    return plan


def plan_week(work: list[Assignment], now: datetime | None = None,
              days: int = 7, daily_minutes: int = DAILY_MINUTES) -> list[Day]:
    now = now or datetime.now(timezone.utc)
    local_now = to_local(now)
    today = local_now.date()

    bedtime = datetime.combine(today, BEDTIME, local_now.tzinfo)
    minutes_left_today = max(0, int((bedtime - local_now).total_seconds() // 60))
    week = [Day(today, min(daily_minutes, minutes_left_today))]
    week += [Day(today + timedelta(days=i), daily_minutes) for i in range(1, days)]
    last_day = week[-1].date

    # Skip work that's too stale to count and work due after this week.
    todo = [p for p in ranked(work, now)
            if not is_stale(p.assignment, now) and last_work_day(p.assignment) <= last_day]
    # Place the tightest deadlines first so they get first pick of days.
    todo.sort(key=lambda p: (last_work_day(p.assignment), -p.score))

    for pick in todo:
        deadline = max(last_work_day(pick.assignment), today)   # overdue → today
        earliest = today
        for session in sessions_for(pick):
            options = [d for d in week if earliest <= d.date <= deadline]
            fits = [d for d in options if d.planned + session.minutes <= d.budget]
            if session.task == "study" and fits:
                # Study close to the test, but before its day: the last study
                # session the day before, an earlier one the day before that.
                target = deadline - timedelta(days=session.parts - session.part + 1)
                chosen = min(fits, key=lambda d: (d.date > target, abs((d.date - target).days)))
            else:
                # Lightest day that fits; if none fit, the lightest day anyway
                # (the plan will show that day as over budget).
                chosen = min(fits or options, key=lambda d: (d.planned, d.date))
            chosen.picks.append(session)
            # Sessions keep their order. The next part of a split assignment
            # (or the next study session) goes on a later day when there is one.
            if session.part < session.parts:
                earliest = min(chosen.date + timedelta(days=1), deadline)
            else:
                earliest = chosen.date

    def order(p: Pick):
        return (-p.score, p.assignment.id, p.task != "study", p.part)
    for day in week:
        day.picks.sort(key=order)
    return week


def spoken_summary(week: list[Day], warn: bool = True) -> str:
    """A short plan to read aloud, e.g. 'Today: Quiz 2 and CH 03 HW.'
    How long things take is left out unless the student asks."""
    today = week[0].date
    parts = []
    for day in week:
        if not day.picks:
            continue
        name = ("Today" if day.date == today
                else "Tomorrow" if day.date == today + timedelta(days=1)
                else f"{day.date:%A}")
        # Parts done back to back on one day are said once.
        titles = []
        for p in day.picks:
            same_day = sum(q.assignment is p.assignment and q.task == p.task for q in day.picks)
            label = p.assignment.name if p.parts > 1 and same_day == p.parts else p.label()
            if label not in titles:
                titles.append(label)
        listed = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + " and " + titles[-1]
        parts.append(f"{name}: {listed}.")
    if not parts:
        return "You're all caught up for the week."
    overloaded = [d for d in week if d.over_budget]
    if overloaded and warn:
        parts.append("Heads up: some days are over your usual study time.")
    return " ".join(parts)


if __name__ == "__main__":
    # Plan your real week: python -m homework_helper.week [minutes per day]
    import sys
    from dotenv import load_dotenv
    from homework_helper.canvas import Canvas, CanvasError

    load_dotenv(".env")
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    daily = int(sys.argv[1]) if len(sys.argv) > 1 else DAILY_MINUTES
    try:
        week = plan_week(Canvas.from_env().assignments(), daily_minutes=daily)
    except CanvasError as err:
        sys.exit(str(err))

    for day in week:
        flag = "  OVER BUDGET" if day.over_budget else ""
        print(f"{day.date:%a %b %d}  ({day.planned}/{day.budget} min){flag}")
        for p in day.picks:
            print(f"    ~{p.minutes:3} min  {p.assignment.title}  "
                  f"(due {to_local(p.assignment.due):%a %b %d, %I:%M %p})")
    print("\nSpoken:", spoken_summary(week))
