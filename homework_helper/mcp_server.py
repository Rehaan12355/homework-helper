"""MCP server: lets Alexa+ (or any AI agent) use Homework Helper.

Each tool returns a `say` field, a short answer ready to be spoken, plus the
details behind it so the agent can answer follow-up questions. Served over
Streamable HTTP at http://localhost:8000/mcp.

Run it:  python -m homework_helper.mcp_server
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from homework_helper import names, plan_settings, reminders, study_sessions
from homework_helper.canvas import Assignment, Canvas
from homework_helper.clock import to_local
from homework_helper.planner import Pick, ranked, what_to_work_on, when
from homework_helper.reminders import spoken_minutes
from homework_helper.week import (BEDTIME, DAILY_MINUTES, Hours, plan_week,
                                  spoken_summary, study_start)

load_dotenv(".env")

server = MCPServer(
    name="homework-helper",
    title="Homework Helper",
    instructions=(
        "Homework Helper reads the student's Canvas assignments and plans "
        "their homework. Every tool returns `say`, a short answer written "
        "to be spoken aloud. Prefer reading it as-is."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def canvas() -> Canvas:
    """The student's Canvas account. Replaced in tests."""
    return Canvas.from_env()


def load_work() -> list[Assignment]:
    """The student's assignments from Canvas, with short spoken names.
    Replaced in tests."""
    return names.add_names(canvas().assignments())


def now() -> datetime:
    return datetime.now(timezone.utc)


def pick_details(p: Pick) -> dict:
    a = p.assignment
    return {"name": a.name, "title": a.title, "course": a.course, "minutes": p.minutes,
            "due": to_local(a.due).isoformat(), "points": a.points,
            "overdue": a.overdue, "why": p.reason, "url": a.url}


def listed(items: list[str], last: str = "and") -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}"


@server.tool(title="What should I work on?", annotations=READ_ONLY)
def what_should_i_work_on(minutes_free: int | None = None) -> dict[str, Any]:
    """The best homework to do right now, weighing due dates, points, and
    overdue work. Pass minutes_free if the student says how much time they
    have (e.g. "I have an hour" -> 60) to get everything that fits."""
    t = now()
    picks = what_to_work_on(load_work(), minutes_free, t)
    if not picks:
        return {"say": "You're all caught up. Nothing is due right now.", "picks": []}
    if minutes_free is None or len(picks) == 1:
        top = picks[0]
        say = f"Work on {top.assignment.name}. {top.reason}"
    else:
        free = spoken_minutes(minutes_free).removeprefix("about ")
        say = (f"With {free} free, you can do "
               f"{listed([p.assignment.name for p in picks])}. Start with "
               f"{picks[0].assignment.name}. {picks[0].reason}")
    return {"say": say, "picks": [pick_details(p) for p in picks]}


def day_name(d, today) -> str:
    return ("Today" if d == today else "Tomorrow" if (d - today).days == 1
            else f"{d:%A}")


def clock_time(dt: datetime) -> str:
    """4:00 PM -> "4 PM", 4:30 PM -> "4:30 PM"."""
    local = to_local(dt)
    return local.strftime("%I:%M %p" if local.minute else "%I %p").lstrip("0")


def session_details(s: study_sessions.Session) -> dict:
    a = s.pick.assignment
    return {"start": to_local(s.start).isoformat(), "end": to_local(s.end).isoformat(),
            "label": s.pick.label(), "task": s.pick.task, "part": s.pick.part,
            "parts": s.pick.parts, "name": a.name, "title": a.title, "course": a.course,
            "due": to_local(a.due).isoformat(), "overdue": a.overdue, "url": a.url}


class BusyTime(BaseModel):
    """A time the student isn't free to study."""
    label: str = Field(description='What it is, e.g. "Gym", "Dinner", "Work"')
    start: str = Field(description='Start time, 24-hour, e.g. "19:00"')
    end: str = Field(description='End time, 24-hour, e.g. "20:00"')
    days: str = Field("today", description=(
        'When: "today", "tomorrow", a weekday like "wednesday" (the next one), '
        '"every day", "weekdays", "weekends", or "every monday"'))


def plan_the_week(t: datetime, minutes_per_day: int):
    """The plan both calendar tools share: the student's saved changes, their
    calendar, and the week placed into what's left."""
    today = to_local(t).date()
    settings = plan_settings.load(today)
    cal_busy, used_calendar = study_sessions.calendar_busy(t)
    days = [today + timedelta(days=i) for i in range(7)]
    mine = settings.busy_times(days, to_local(t).tzinfo)
    hours = Hours(start=settings.study_start or study_start(),
                  bedtime=settings.bedtime or BEDTIME,
                  busy=cal_busy + [(a, b) for a, b, _ in mine])
    week = plan_week(load_work(), t, daily_minutes=minutes_per_day, hours=hours)
    return week, hours, mine, used_calendar


@server.tool(title="Plan my week",
             annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                         idempotentHint=True, openWorldHint=True))
def plan_my_week(minutes_per_day: int = DAILY_MINUTES,
                 busy: list[BusyTime] | None = None,
                 bedtime: str | None = None,
                 start_time: str | None = None,
                 remove: list[str] | None = None) -> dict[str, Any]:
    """A study schedule for the next 7 days, with times. Every assignment
    is placed on a day before it's due, within a daily study-time budget,
    with study time before quizzes and tests, and long work split across
    days. Fits around the student's Google Calendar when it's connected.

    To change the plan, call again with the change; it's remembered for
    later plans: `busy` for times they're not free ("gym from 7 to 8"),
    `bedtime` ("I'm sleeping at 10" -> "22:00"), `start_time` for when they
    can start studying ("I get home at 5" -> "17:00"), `remove` to undo a
    busy time by its label ("Gym"), or "bedtime", "start time", or "all".
    Doesn't change the calendar; add_study_sessions does that."""
    t = now()
    today = to_local(t).date()
    notes = []
    if busy or bedtime or start_time or remove:
        settings = plan_settings.load(today)
        try:
            notes = plan_settings.change(
                settings, today, busy=[b.model_dump() for b in busy or []],
                bedtime=bedtime, study_start=start_time, remove=remove)
        except plan_settings.SettingsError as err:
            return {"say": f"{err} Could you say it another way?", "days": []}
        plan_settings.save(settings)

    week, hours, mine, used_calendar = plan_the_week(t, minutes_per_day)
    sessions, unplaced = study_sessions.schedule(week, [], t, hours)

    # Spoken: where to start and the first day. The whole week is in
    # `whole_week` (and on screen, on a device that has one).
    whole_week = spoken_summary(week)
    say = f"Got it: {listed(notes)}. Here's the new plan. " if notes else ""
    if sessions:
        first = sessions[0]
        start_day = to_local(first.start).date()
        doing = (f"studying for {first.pick.assignment.name}" if first.pick.task == "study"
                 else first.pick.assignment.name)
        say += (f"Start {day_name(start_day, today).lower()} at {clock_time(first.start)} "
                f"with {doing}. ") + spoken_summary(
                    [d for d in week if d.date == start_day], warn=False)
        later = [s for s in sessions if to_local(s.start).date() > start_day]
        if later:
            last = day_name(to_local(later[-1].start).date(), today)
            say += (f" After that, {len(later)} more session{'s' if len(later) != 1 else ''}"
                    f" through {last}.")
        if any(d.over_budget for d in week):
            say += " Some days run over your usual study time."
    else:
        say += whole_week
    if unplaced:
        say += f" I couldn't find time for {listed([p.label() for p in unplaced])}."
    return {
        "say": say,
        "whole_week": whole_week,
        "fits_your_calendar": used_calendar,
        "study_hours": {"start": clock_time(datetime.combine(today, hours.start, to_local(t).tzinfo)),
                        "bedtime": clock_time(datetime.combine(today, hours.bedtime, to_local(t).tzinfo))},
        "days": [{"date": d.date.isoformat(), "day": day_name(d.date, today),
                  "over_budget": d.over_budget,
                  "sessions": [session_details(s) for s in sessions
                               if to_local(s.start).date() == d.date],
                  "busy": [{"label": label, "start": a.isoformat(), "end": b.isoformat()}
                           for a, b, label in mine if a.date() == d.date]} for d in week],
        "no_time_for": [p.label() for p in unplaced],
    }


@server.tool(title="Upcoming assignments", annotations=READ_ONLY)
def list_assignments() -> dict[str, Any]:
    """Every unfinished assignment, most important first, with due dates."""
    t = now()
    picks = ranked(load_work(), t)
    if not picks:
        return {"say": "You have no unfinished assignments.", "assignments": []}
    first = picks[:3]
    say = (f"You have {len(picks)} unfinished assignment{'s' if len(picks) != 1 else ''}. "
           + " ".join(f"{p.assignment.name}, due {when(p.assignment.due, t)}." for p in first))
    return {"say": say, "assignments": [pick_details(p) for p in picks]}


@server.tool(title="Check reminders", annotations=READ_ONLY)
def check_reminders() -> dict[str, Any]:
    """Work that's due within a day, due within 3 hours, or overdue, and not
    submitted. Use when the student asks "anything due soon?"."""
    found = reminders.due_reminders(load_work(), now())
    if not found:
        return {"say": "Nothing is due in the next day.", "reminders": []}
    return {"say": " ".join(r.text for r in found),
            "reminders": [{"stage": r.stage, "name": r.assignment.name,
                           "text": r.text} for r in found]}


@server.tool(title="Add study sessions to calendar",
             annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                         idempotentHint=True, openWorldHint=True))
def add_study_sessions(minutes_per_day: int = DAILY_MINUTES) -> dict[str, Any]:
    """Puts this week's plan on the student's Google Calendar as study
    sessions in free time. Re-running replaces earlier sessions; the
    student's own events are never changed. Only call this when the student
    asks to add or update study time on their calendar. Uses the changes
    the student made with plan_my_week (busy times, bedtime)."""
    t = now()
    week, hours, _, _ = plan_the_week(t, minutes_per_day)
    sessions, unplaced = study_sessions.sync(study_sessions.google_calendar(), week, t,
                                             hours=hours)
    say = f"I added {len(sessions)} study session{'s' if len(sessions) != 1 else ''} to your calendar."
    if sessions:
        first = sessions[0]
        start = to_local(first.start).strftime("%I:%M %p").lstrip("0")
        say += f" The first is {first.pick.label()} at {start}."
    if unplaced:
        say += f" I couldn't find free time for {listed([p.label() for p in unplaced])}."
    return {"say": say,
            "sessions": [{"label": s.pick.label(), "start": to_local(s.start).isoformat(),
                          "end": to_local(s.end).isoformat()} for s in sessions],
            "no_time_for": [p.label() for p in unplaced]}


@server.tool(title="Mark an assignment done",
             annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                         idempotentHint=True, openWorldHint=True))
def mark_complete(assignment: str, done: bool = True) -> dict[str, Any]:
    """Marks an assignment done in Canvas (the "mark as done" checkbox in the
    Canvas planner and To Do list; it doesn't submit anything). Use when the
    student says they finished something or asks to mark it done. Pass the
    assignment as they said it, e.g. "free fall pre-lab". Pass done=false to
    undo. If several assignments match, nothing changes and `matches` lists
    them so you can ask which one."""
    work = load_work()
    found = names.find(work, assignment, done)
    if not found:
        return {"say": f"I couldn't find an assignment called {assignment}.",
                "matches": [], "marked": None}
    if len(found) > 1:
        return {"say": f"Which one: {listed([a.name for a in found], 'or')}?",
                "matches": [a.name for a in found], "marked": None}
    a = found[0]
    canvas().mark_done(a, done)
    if not done:
        return {"say": f"Okay, {a.name} is back on your list.", "matches": [], "marked": a.name}
    say = f"Done, I marked {a.name} as done in Canvas."
    picks = what_to_work_on(work, None, now())
    if picks:
        say += f" Next up is {picks[0].assignment.name}."
    return {"say": say, "matches": [], "marked": a.name}


if __name__ == "__main__":
    server.run("streamable-http",
               host=os.environ.get("MCP_HOST", "127.0.0.1"),
               port=int(os.environ.get("MCP_PORT", "8000")),
               stateless_http=True, json_response=True)
