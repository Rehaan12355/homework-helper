"""Puts the week plan on Google Calendar as study sessions.

Each planned assignment becomes a time block on the day the week plan chose,
in free time between STUDY_START and bedtime. Existing events (practice,
class, dinner) are worked around. Sessions are tagged, so re-running replaces
the old plan instead of piling up duplicates, and the student's own events
are never touched.
"""

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from homework_helper.clock import local_tz, to_local
from homework_helper.planner import Pick
from homework_helper.week import BEDTIME, Day

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TAG = "homeworkHelper"                 # marks events this app created
BREAK = timedelta(minutes=10)          # rest between sessions
STEP = timedelta(minutes=5)            # sessions start on 5-minute marks


@dataclass
class Session:
    pick: Pick
    start: datetime
    end: datetime


def study_start() -> time:
    """When study time begins each day, from STUDY_START (e.g. "16:00")."""
    hours, minutes = os.environ.get("STUDY_START", "16:00").split(":")
    return time(int(hours), int(minutes))


def round_up(dt: datetime) -> datetime:
    extra = (dt - dt.replace(minute=0, second=0, microsecond=0)) % STEP
    return dt + (STEP - extra) if extra else dt


def is_ours(event: dict) -> bool:
    private = event.get("extendedProperties", {}).get("private", {})
    return private.get(TAG) == "1"


def parse_event_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def busy_times(events: list[dict], now: datetime) -> list[tuple[datetime, datetime]]:
    """The times the student is already busy, from their calendar events.

    All-day events, events marked "free", and declined invites don't block
    time. Our own future sessions don't either, since they get replaced.
    """
    busy = []
    for e in events:
        if "dateTime" not in e.get("start", {}) or e.get("status") == "cancelled":
            continue
        if e.get("transparency") == "transparent":
            continue
        if any(a.get("self") and a.get("responseStatus") == "declined"
               for a in e.get("attendees", [])):
            continue
        start, end = parse_event_time(e["start"]["dateTime"]), parse_event_time(e["end"]["dateTime"])
        if is_ours(e) and start >= now:
            continue
        busy.append((start, end))
    return sorted(busy)


def first_free(start: datetime, length: timedelta, close: datetime,
               busy: list[tuple[datetime, datetime]]) -> datetime | None:
    """The earliest time from `start` with `length` free before `close`."""
    t = round_up(start)
    moved = True
    while moved:
        moved = False
        for b_start, b_end in busy:
            if b_start < t + length and b_end > t:      # overlaps
                t = round_up(b_end)
                moved = True
    return t if t + length <= close else None


def schedule(week: list[Day], busy: list[tuple[datetime, datetime]],
             now: datetime | None = None) -> tuple[list[Session], list[Pick]]:
    """Places each day's work into free time. Returns the sessions, and the
    work that didn't fit anywhere that day."""
    now = now or datetime.now(timezone.utc)
    tz = to_local(now).tzinfo
    sessions, unplaced = [], []
    for day in week:
        cursor = datetime.combine(day.date, study_start(), tz)
        cursor = max(cursor, to_local(now))
        close = datetime.combine(day.date, BEDTIME, tz)
        for pick in day.picks:
            length = timedelta(minutes=pick.minutes)
            start = first_free(cursor, length, close, busy)
            if start is None:
                unplaced.append(pick)
                continue
            sessions.append(Session(pick, start, start + length))
            cursor = start + length + BREAK
    return sessions, unplaced


def event_body(s: Session) -> dict:
    a = s.pick.assignment
    tz = local_tz()
    def when(dt):
        body = {"dateTime": to_local(dt).isoformat()}
        if tz is not None:
            body["timeZone"] = tz.key
        return body
    return {
        "summary": f"Study: {a.title}",
        "description": f"{a.course}\n{s.pick.reason}\n{a.url}".strip(),
        "start": when(s.start),
        "end": when(s.end),
        "reminders": {"useDefault": False,
                      "overrides": [{"method": "popup", "minutes": 5}]},
        "extendedProperties": {"private": {TAG: "1", "assignmentId": str(a.id)}},
    }


# --- Google Calendar -------------------------------------------------------

def google_calendar():
    """Signs in to Google Calendar. The first run opens a browser window."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    client_file = os.environ.get("GOOGLE_CREDENTIALS", "credentials.json")
    token_file = os.environ.get("GOOGLE_TOKEN", "token.json")
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_file):
                raise SystemExit(f"{client_file} not found. Download the OAuth "
                                 "client from Google Cloud (see README).")
            flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_events(service, start: datetime, end: datetime, calendar_id: str = "primary",
                **filters) -> list[dict]:
    events, page = [], None
    while True:
        result = service.events().list(
            calendarId=calendar_id, timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime", pageToken=page, **filters).execute()
        events += result.get("items", [])
        page = result.get("nextPageToken")
        if not page:
            return events


def sync(service, week: list[Day], now: datetime | None = None,
         calendar_id: str = "primary") -> tuple[list[Session], list[Pick]]:
    """Replaces this app's upcoming study sessions with the current plan."""
    now = now or datetime.now(timezone.utc)
    end = datetime.combine(week[-1].date + timedelta(days=1), time(0), to_local(now).tzinfo)
    events = list_events(service, now, end, calendar_id)
    sessions, unplaced = schedule(week, busy_times(events, now), now)

    for e in events:
        if is_ours(e) and parse_event_time(e["start"]["dateTime"]) >= now:
            service.events().delete(calendarId=calendar_id, eventId=e["id"]).execute()
    for s in sessions:
        service.events().insert(calendarId=calendar_id, body=event_body(s)).execute()
    return sessions, unplaced


if __name__ == "__main__":
    # Put your week plan on Google Calendar:
    #   python -m homework_helper.study_sessions            (preview only)
    #   python -m homework_helper.study_sessions --sync     (add to calendar)
    import sys
    from dotenv import load_dotenv
    from homework_helper.canvas import Canvas, CanvasError
    from homework_helper.week import plan_week

    load_dotenv(".env")
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    try:
        week = plan_week(Canvas.from_env().assignments())
    except CanvasError as err:
        sys.exit(str(err))

    service = google_calendar()
    now = datetime.now(timezone.utc)
    if "--sync" in sys.argv:
        sessions, unplaced = sync(service, week, now)
        print(f"Added {len(sessions)} study sessions to Google Calendar.")
    else:
        end = datetime.combine(week[-1].date + timedelta(days=1), time(0), to_local(now).tzinfo)
        busy = busy_times(list_events(service, now, end), now)
        sessions, unplaced = schedule(week, busy, now)
        print("Preview (run with --sync to add these):")
    for s in sessions:
        print(f"  {to_local(s.start):%a %b %d  %I:%M}-{to_local(s.end):%I:%M %p}  "
              f"{s.pick.assignment.title}")
    for p in unplaced:
        print(f"  NO FREE TIME: {p.assignment.title} (~{p.minutes} min)")
