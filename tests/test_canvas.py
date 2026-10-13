import pytest

from homework_helper.canvas import Canvas, CanvasError

BASE = "https://school.instructure.com"


class FakeResponse:
    def __init__(self, data, status=200, next_url=None):
        self._data = data
        self.status_code = status
        self.ok = status < 400
        self.links = {"next": {"url": next_url}} if next_url else {}

    def json(self):
        return self._data


def planner_item(**overrides):
    item = {
        "plannable_type": "assignment",
        "plannable_id": 1,
        "course_id": 10,
        "context_name": "General Physics I",
        "html_url": "/courses/10/assignments/1",
        "plannable_date": "2026-10-15T06:59:00Z",
        "plannable": {"title": "CH 04 HW", "due_at": "2026-10-15T06:59:00Z",
                      "points_possible": 20.0},
        "submissions": {"submitted": False, "missing": False, "graded": False},
        "planner_override": None,
    }
    item.update(overrides)
    return item


def canvas_with(pages):
    """A Canvas client whose requests return the given pages in order."""
    canvas = Canvas(BASE + "/", "token")
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return pages[len(calls) - 1]

    canvas.session.get = fake_get
    return canvas, calls


def test_parses_assignment_fields():
    canvas, _ = canvas_with([FakeResponse([planner_item()])])
    [a] = canvas.assignments()
    assert a.title == "CH 04 HW"
    assert a.course == "General Physics I"
    assert a.points == 20.0
    assert a.url == BASE + "/courses/10/assignments/1"
    assert a.due.year == 2026 and a.due.tzinfo is not None
    assert not a.done and not a.missing


def test_skips_non_work_items_and_items_without_dates():
    canvas, _ = canvas_with([FakeResponse([
        planner_item(plannable_type="announcement"),
        planner_item(plannable_type="planner_note"),
        planner_item(plannable_date=None, plannable={"title": "No date"}),
        planner_item(plannable_type="quiz", plannable_id=2),
    ])])
    work = canvas.assignments()
    assert [a.kind for a in work] == ["quiz"]


def test_submission_states():
    def item(n, **kw):    # distinct titles so they aren't merged as duplicates
        return planner_item(plannable_id=n, plannable={
            "title": f"Work {n}", "due_at": "2026-10-15T06:59:00Z"}, **kw)

    canvas, _ = canvas_with([FakeResponse([
        item(1, submissions={"submitted": True}),
        item(2, submissions={"excused": True}),
        item(3, submissions={"graded": True}),
        item(4, submissions={"missing": True}),
        item(5, submissions=False),   # can't be submitted
        item(6, planner_override={"marked_complete": True}),
    ])])
    by_id = {a.id: a for a in canvas.assignments()}
    assert by_id[1].done and by_id[2].done and by_id[3].done and by_id[6].done
    assert not by_id[4].done and by_id[4].missing
    assert not by_id[5].done


def test_follows_pages_and_sorts_by_due_date():
    canvas, calls = canvas_with([
        FakeResponse([planner_item(plannable_id=1, plannable={
            "title": "Later", "due_at": "2026-10-20T00:00:00Z"})], next_url="PAGE2"),
        FakeResponse([planner_item(plannable_id=2, plannable={
            "title": "Sooner", "due_at": "2026-10-12T00:00:00Z"})]),
    ])
    assert [a.title for a in canvas.assignments()] == ["Sooner", "Later"]
    assert calls[1] == ("PAGE2", None)     # page 2 URL already has its params


def test_bad_token_gives_clear_error():
    canvas, _ = canvas_with([FakeResponse({}, status=401)])
    with pytest.raises(CanvasError, match="access token"):
        canvas.assignments()


def test_from_env_requires_settings(monkeypatch):
    monkeypatch.delenv("CANVAS_URL", raising=False)
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    with pytest.raises(CanvasError, match="CANVAS_URL"):
        Canvas.from_env()


def test_merges_publisher_duplicates():
    # Pearson-style pair: teacher's 5-point link (never submitted) and the
    # 10-point graded entry, due an hour apart.
    canvas, _ = canvas_with([FakeResponse([
        planner_item(plannable_id=1, plannable={
            "title": "Chapter 3 pre-lecture", "due_at": "2026-10-07T17:30:00Z",
            "points_possible": 2.5}, submissions={"submitted": False}),
        planner_item(plannable_id=2, plannable={
            "title": "Chapter 3 pre-lecture ", "due_at": "2026-10-07T18:30:00Z",
            "points_possible": 10.0}, submissions={"submitted": True, "graded": True}),
    ])])
    [a] = canvas.assignments()
    assert a.done and a.points == 10.0 and a.id == 2


def test_does_not_merge_different_work():
    canvas, _ = canvas_with([FakeResponse([
        # same title, different weeks
        planner_item(plannable_id=1, plannable={"title": "Reading", "due_at": "2026-10-01T00:00:00Z"}),
        planner_item(plannable_id=2, plannable={"title": "Reading", "due_at": "2026-10-08T00:00:00Z"}),
        # same title and day, different course
        planner_item(plannable_id=3, course_id=99, plannable={"title": "Reading", "due_at": "2026-10-01T00:00:00Z"}),
    ])])
    assert sorted(a.id for a in canvas.assignments()) == [1, 2, 3]


def test_overdue_uses_due_date_not_just_canvas_flag():
    canvas, _ = canvas_with([FakeResponse([
        planner_item(plannable_id=1, plannable={"title": "Past", "due_at": "2020-01-01T00:00:00Z"},
                     submissions={"submitted": False, "missing": False}),
        planner_item(plannable_id=2, plannable={"title": "Past done", "due_at": "2020-01-01T00:00:00Z"},
                     submissions={"submitted": True}),
        planner_item(plannable_id=3, plannable={"title": "Future", "due_at": "2099-01-01T00:00:00Z"}),
    ])])
    by_id = {a.id: a for a in canvas.assignments()}
    assert by_id[1].overdue
    assert not by_id[2].overdue and not by_id[3].overdue


def canvas_recording_writes(reply):
    canvas = Canvas(BASE, "token")
    sent = []

    def fake_request(method, url, json=None, timeout=None):
        sent.append((method, url, json))
        return FakeResponse(reply)

    canvas.session.request = fake_request
    return canvas, sent


def test_mark_done_creates_a_planner_override():
    canvas, _ = canvas_with([FakeResponse([planner_item(plannable_type="quiz", plannable_id=7)])])
    [a] = canvas.assignments()
    canvas, sent = canvas_recording_writes({"id": 55})
    canvas.mark_done(a)
    assert sent == [("POST", BASE + "/api/v1/planner/overrides",
                     {"plannable_type": "quiz", "plannable_id": 7, "marked_complete": True})]
    assert a.done and a.override_id == 55


def test_mark_done_updates_an_existing_override():
    canvas, _ = canvas_with([FakeResponse([planner_item(
        planner_override={"id": 55, "marked_complete": True})])])
    [a] = canvas.assignments()
    assert a.done and a.override_id == 55
    canvas, sent = canvas_recording_writes({"id": 55})
    canvas.mark_done(a, done=False)
    assert sent == [("PUT", BASE + "/api/v1/planner/overrides/55", {"marked_complete": False})]
    assert not a.done


def test_mark_done_reports_canvas_errors():
    canvas, _ = canvas_with([FakeResponse([planner_item()])])
    [a] = canvas.assignments()
    canvas.session.request = lambda *args, **kw: FakeResponse({}, status=403)
    with pytest.raises(CanvasError, match="403"):
        canvas.mark_done(a)
