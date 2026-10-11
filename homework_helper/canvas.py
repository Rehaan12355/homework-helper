"""Reads a student's upcoming work from Canvas.

Uses the Canvas planner API, which returns everything due across all courses
(assignments, quizzes, discussions) in one request, along with whether each
one has been submitted.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

# Planner item types that are actual work to do. The planner also returns
# announcements, notes, and calendar events, which we skip.
WORK_TYPES = {"assignment", "quiz", "discussion_topic", "sub_assignment"}


class CanvasError(Exception):
    """A problem talking to Canvas, with a message safe to show the user."""


@dataclass
class Assignment:
    id: int
    course_id: int
    course: str
    title: str
    kind: str                 # "assignment", "quiz", or "discussion_topic"
    due: datetime
    points: float | None
    url: str
    submitted: bool
    missing: bool             # past due and not submitted, per Canvas
    graded: bool
    locks: datetime | None = None   # after this, Canvas won't accept it

    @property
    def done(self) -> bool:
        return self.submitted or self.graded

    @property
    def overdue(self) -> bool:
        # Canvas only sets "missing" for work submitted in Canvas itself, not
        # for homework on outside sites (like Pearson), so check the date too.
        return not self.done and self.due < datetime.now(timezone.utc)

    @property
    def locked(self) -> bool:
        return self.locks is not None and self.locks < datetime.now(timezone.utc)


class Canvas:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def from_env(cls) -> "Canvas":
        url, token = os.environ.get("CANVAS_URL"), os.environ.get("CANVAS_TOKEN")
        if not url or not token:
            raise CanvasError("Set CANVAS_URL and CANVAS_TOKEN (see .env.example).")
        return cls(url, token)

    def _get_all(self, path: str, params: dict) -> list[dict]:
        """GET a Canvas list endpoint, following its page links."""
        url = f"{self.base_url}/api/v1{path}"
        params = {"per_page": 100, **params}
        items = []
        while url:
            try:
                resp = self.session.get(url, params=params, timeout=20)
            except requests.RequestException as err:
                raise CanvasError(f"Couldn't reach Canvas: {err}") from err
            if resp.status_code == 401:
                raise CanvasError("Canvas rejected the access token. It may have expired.")
            if not resp.ok:
                raise CanvasError(f"Canvas returned an error ({resp.status_code}).")
            items.extend(resp.json())
            url = resp.links.get("next", {}).get("url")
            params = None              # the next-page URL already includes them
        return items

    def assignments(self, days_back: int = 14, days_ahead: int = 30) -> list[Assignment]:
        """Work due between `days_back` days ago and `days_ahead` days from now,
        sorted by due date."""
        now = datetime.now(timezone.utc)
        items = self._get_all("/planner/items", {
            "start_date": (now - timedelta(days=days_back)).isoformat(),
            "end_date": (now + timedelta(days=days_ahead)).isoformat(),
        })
        found = [a for a in (self._parse(item) for item in items) if a]
        return merge_duplicates(sorted(found, key=lambda a: a.due))

    def _parse(self, item: dict) -> Assignment | None:
        if item.get("plannable_type") not in WORK_TYPES:
            return None
        plannable = item.get("plannable") or {}
        due = plannable.get("due_at") or item.get("plannable_date")
        if not due:
            return None

        # "submissions" is false for items that can't be submitted.
        subs = item.get("submissions") or {}
        # Students can tick "mark as done" in the Canvas planner themselves.
        marked_done = bool((item.get("planner_override") or {}).get("marked_complete"))

        url = item.get("html_url") or ""
        if url.startswith("/"):
            url = self.base_url + url

        return Assignment(
            id=item["plannable_id"],
            course_id=item.get("course_id") or 0,
            course=item.get("context_name") or "Unknown course",
            title=plannable.get("title") or plannable.get("name") or "Untitled",
            kind=item["plannable_type"],
            due=parse_time(due),
            points=plannable.get("points_possible"),
            url=url,
            submitted=bool(subs.get("submitted") or subs.get("excused")) or marked_done,
            missing=bool(subs.get("missing")),
            graded=bool(subs.get("graded")),
            locks=parse_time(plannable["lock_at"]) if plannable.get("lock_at") else None,
        )


def parse_time(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def merge_duplicates(work: list[Assignment]) -> list[Assignment]:
    """Combine entries for the same piece of homework.

    Publisher homework (e.g. Pearson Mastering) often shows up twice in
    Canvas: the link the teacher created, and a second entry the publisher
    creates when it sends the grade back. Only the second one is ever marked
    submitted, so without merging, finished homework looks undone forever.
    Entries match when they're in the same course, have the same title, and
    are due within a day of each other.
    """
    merged: list[Assignment] = []
    for a in work:
        twin = next((m for m in merged
                     if m.course_id == a.course_id
                     and m.title.strip().lower() == a.title.strip().lower()
                     and abs(m.due - a.due) <= timedelta(days=1)), None)
        if twin is None:
            merged.append(a)
            continue
        # Keep the copy that has the grade, but count it done if either is.
        keep = a if (a.done and not twin.done) else twin
        keep.submitted = twin.submitted or a.submitted
        keep.graded = twin.graded or a.graded
        keep.missing = keep.missing and not keep.done
        merged[merged.index(twin)] = keep
    # The kept copy's due date may differ slightly, so sort again.
    return sorted(merged, key=lambda a: a.due)


if __name__ == "__main__":
    # Quick check against your real Canvas account: python -m homework_helper.canvas
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    if sys.stdout:
        sys.stdout.reconfigure(errors="replace")
    try:
        work = Canvas.from_env().assignments()
    except CanvasError as err:
        sys.exit(str(err))
    for a in work:
        status = "done" if a.done else "OVERDUE" if a.overdue else "to do"
        points = f"{a.points:g} pts" if a.points else "no pts"
        print(f"{a.due.astimezone():%a %b %d %I:%M %p}  [{status:7}]  "
              f"{a.course[:25]:25}  {a.title}  ({points})")
    print(f"\n{len(work)} items, {sum(not a.done for a in work)} still to do.")
