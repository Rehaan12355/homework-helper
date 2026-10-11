"""Plans the student's week: which homework to do on which day.

Each assignment is placed on a day before it's due. Work is spread out
instead of piled onto today: the most urgent work is placed first, each on
the lightest day that still beats its deadline. Every day has a time budget,
and today only counts the time left before bedtime.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from homework_helper.canvas import Assignment
from homework_helper.clock import to_local
from homework_helper.planner import Pick, is_stale, ranked

DAILY_MINUTES = 120
BEDTIME = time(23, 0)
# Work due before this hour has to be finished the day before.
MORNING_CUTOFF = time(12, 0)


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


def last_work_day(a: Assignment) -> date:
    """The last day this can realistically be worked on."""
    due = to_local(a.due)
    return due.date() - timedelta(days=1) if due.time() < MORNING_CUTOFF else due.date()


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
        options = [d for d in week if d.date <= deadline]
        fits = [d for d in options if d.planned + pick.minutes <= d.budget]
        # Lightest day that fits; if none fit, the lightest day anyway
        # (the plan will show that day as over budget).
        chosen = min(fits or options, key=lambda d: (d.planned, d.date))
        chosen.picks.append(pick)

    for day in week:
        day.picks.sort(key=lambda p: -p.score)
    return week


def spoken_summary(week: list[Day]) -> str:
    """A short plan to read aloud, e.g. 'Today: Quiz 2, about 30 minutes.'"""
    today = week[0].date
    parts = []
    for day in week:
        if not day.picks:
            continue
        name = ("Today" if day.date == today
                else "Tomorrow" if day.date == today + timedelta(days=1)
                else f"{day.date:%A}")
        titles = [p.assignment.title for p in day.picks]
        listed = titles[0] if len(titles) == 1 else ", ".join(titles[:-1]) + " and " + titles[-1]
        parts.append(f"{name}: {listed}, about {day.planned} minutes.")
    if not parts:
        return "You're all caught up for the week."
    overloaded = [d for d in week if d.over_budget]
    if overloaded:
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
