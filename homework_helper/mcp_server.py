"""MCP server: lets Alexa+ (or any AI agent) use Homework Helper.

Each tool returns a `say` field, a short answer ready to be spoken, plus the
details behind it so the agent can answer follow-up questions. Served over
Streamable HTTP at http://localhost:8000/mcp.

Run it:  python -m homework_helper.mcp_server
"""

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from homework_helper import reminders, study_sessions
from homework_helper.canvas import Assignment, Canvas
from homework_helper.clock import to_local
from homework_helper.planner import Pick, ranked, what_to_work_on, when
from homework_helper.reminders import spoken_minutes
from homework_helper.week import DAILY_MINUTES, plan_week, spoken_summary

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


def load_work() -> list[Assignment]:
    """The student's assignments from Canvas. Replaced in tests."""
    return Canvas.from_env().assignments()


def now() -> datetime:
    return datetime.now(timezone.utc)


def pick_details(p: Pick) -> dict:
    a = p.assignment
    return {"title": a.title, "course": a.course, "minutes": p.minutes,
            "due": to_local(a.due).isoformat(), "points": a.points,
            "overdue": a.overdue, "why": p.reason, "url": a.url}


def listed(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


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
        say = f"Work on {top.assignment.title}. {top.reason}"
    else:
        total = sum(p.minutes for p in picks)
        free = spoken_minutes(minutes_free).removeprefix("about ")
        say = (f"With {free} free, you can do "
               f"{listed([p.assignment.title for p in picks])}, "
               f"{spoken_minutes(total)} total. Start with "
               f"{picks[0].assignment.title}. {picks[0].reason}")
    return {"say": say, "picks": [pick_details(p) for p in picks]}


@server.tool(title="Plan my week", annotations=READ_ONLY)
def plan_my_week(minutes_per_day: int = DAILY_MINUTES) -> dict[str, Any]:
    """Spreads the student's homework across the next 7 days, each
    assignment on a day before it's due, within a daily study-time budget."""
    week = plan_week(load_work(), now(), daily_minutes=minutes_per_day)
    return {
        "say": spoken_summary(week),
        "days": [{"date": d.date.isoformat(), "planned_minutes": d.planned,
                  "budget_minutes": d.budget, "over_budget": d.over_budget,
                  "work": [pick_details(p) for p in d.picks]} for d in week],
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
           + " ".join(f"{p.assignment.title}, due {when(p.assignment.due, t)}." for p in first))
    return {"say": say, "assignments": [pick_details(p) for p in picks]}


@server.tool(title="Check reminders", annotations=READ_ONLY)
def check_reminders() -> dict[str, Any]:
    """Work that's due within a day, due within 3 hours, or overdue, and not
    submitted. Use when the student asks "anything due soon?"."""
    found = reminders.due_reminders(load_work(), now())
    if not found:
        return {"say": "Nothing is due in the next day.", "reminders": []}
    return {"say": " ".join(r.text for r in found),
            "reminders": [{"stage": r.stage, "title": r.assignment.title,
                           "text": r.text} for r in found]}


@server.tool(title="Add study sessions to calendar",
             annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                         idempotentHint=True, openWorldHint=True))
def add_study_sessions(minutes_per_day: int = DAILY_MINUTES) -> dict[str, Any]:
    """Puts this week's plan on the student's Google Calendar as study
    sessions in free time. Re-running replaces earlier sessions; the
    student's own events are never changed. Only call this when the student
    asks to add or update study time on their calendar."""
    t = now()
    week = plan_week(load_work(), t, daily_minutes=minutes_per_day)
    sessions, unplaced = study_sessions.sync(study_sessions.google_calendar(), week, t)
    say = f"I added {len(sessions)} study session{'s' if len(sessions) != 1 else ''} to your calendar."
    if sessions:
        first = sessions[0]
        start = to_local(first.start).strftime("%I:%M %p").lstrip("0")
        say += f" The first is {first.pick.assignment.title} at {start}."
    if unplaced:
        say += f" I couldn't find free time for {listed([p.assignment.title for p in unplaced])}."
    return {"say": say,
            "sessions": [{"title": s.pick.assignment.title, "start": to_local(s.start).isoformat(),
                          "end": to_local(s.end).isoformat()} for s in sessions],
            "no_time_for": [p.assignment.title for p in unplaced]}


if __name__ == "__main__":
    server.run("streamable-http",
               host=os.environ.get("MCP_HOST", "127.0.0.1"),
               port=int(os.environ.get("MCP_PORT", "8000")),
               stateless_http=True, json_response=True)
