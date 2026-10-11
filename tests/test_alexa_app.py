from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from homework_helper import alexa_app, mcp_server, reminders
from homework_helper.canvas import Assignment


class FakeAgent:
    """Stands in for the Bedrock agent: remembers what it was asked."""

    def __init__(self):
        self.heard = []

    def __call__(self, text):
        self.heard.append(text)
        return f"  You said: {text}  "


@pytest.fixture
def app(monkeypatch, tmp_path):
    agents = []
    monkeypatch.setattr(alexa_app, "build_agent", lambda: agents.append(FakeAgent()) or agents[-1])
    due_soon = Assignment(id=1, course_id=1, course="Physics", title="CH 03 HW",
                          kind="assignment", due=datetime.now(timezone.utc) + timedelta(hours=2),
                          points=10.0, url="", submitted=False, missing=False, graded=False)
    monkeypatch.setattr(mcp_server, "load_work", lambda: [due_soon])
    assistant = alexa_app.Assistant(reminders.SentLog(str(tmp_path / "sent.json")))
    with TestClient(alexa_app.create_app(assistant),
                    base_url="http://127.0.0.1:8000") as client:   # runs app startup
        client.agents = agents
        yield client


def test_serves_the_page(app):
    page = app.get("/")
    assert page.status_code == 200 and "Homework Helper" in page.text


def test_asks_the_agent_and_keeps_the_conversation(app):
    assert app.post("/api/ask", json={"text": "plan my week"}).json() == {"reply": "You said: plan my week"}
    app.post("/api/ask", json={"text": "and tomorrow?"})
    assert len(app.agents) == 1 and app.agents[0].heard == ["plan my week", "and tomorrow?"]


def test_new_conversation_starts_a_fresh_agent(app):
    app.post("/api/ask", json={"text": "hi"})
    app.post("/api/reset")
    app.post("/api/ask", json={"text": "hi again"})
    assert len(app.agents) == 2


def test_errors_are_spoken_simply(app, monkeypatch):
    def broken():
        raise RuntimeError("AccessDeniedException: Your account is currently being verified.")
    monkeypatch.setattr(alexa_app, "build_agent", broken)
    reply = app.post("/api/ask", json={"text": "hi"}).json()
    assert reply["error"] and "still being verified" in reply["reply"]


def test_new_reminders_become_notifications_once(app):
    assert app.get("/api/notifications").json() == {"count": 1}
    assert app.get("/api/notifications").json() == {"count": 1}   # not added twice
    read = app.post("/api/notifications").json()["notifications"]
    assert read[0].startswith("Heads up: CH 03 HW is due in")
    assert app.get("/api/notifications").json() == {"count": 0}


def test_mcp_endpoint_is_served_alongside(app):
    reply = app.post("/mcp", headers={"Accept": "application/json, text/event-stream"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"}}})
    assert reply.json()["result"]["protocolVersion"] == "2025-11-25"


def test_usage_limit_is_explained(app, monkeypatch):
    def throttled():
        raise RuntimeError("ThrottlingException: Too many tokens per day, please wait")
    monkeypatch.setattr(alexa_app, "build_agent", throttled)
    assert "usage limit" in app.post("/api/ask", json={"text": "hi"}).json()["reply"]
