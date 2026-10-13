from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from homework_helper import alexa_app, cloud, mcp_server, names, store
from homework_helper.canvas import Assignment

KEY = "a-long-test-key-0123456789"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}}}
HEADERS = {"Accept": "application/json, text/event-stream"}


class FakeTable:
    """Just enough of a boto3 DynamoDB Table for the store."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["pk"], Item["sk"])] = Item

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def delete_item(self, Key):
        self.items.pop((Key["pk"], Key["sk"]), None)

    def batch_writer(self):
        return self      # put_item works the same; used as a context manager

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def query(self, KeyConditionExpression):
        pk = KeyConditionExpression.get_expression()["values"][1]
        return {"Items": [v for (p, s), v in sorted(self.items.items()) if p == pk]}


def due_in(hours, id=1):
    return Assignment(id=id, course_id=1, course="Physics", title=f"HW {id}",
                      kind="assignment", due=datetime.now(timezone.utc) + timedelta(hours=hours),
                      points=10.0, url="", submitted=False, missing=False, graded=False)


@pytest.fixture
def mcp_client(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_work", lambda: [due_in(2)])
    with TestClient(cloud.create_mcp_app(KEY),
                    base_url="https://abc.lambda-url.us-west-2.on.aws") as client:
        yield client


def test_mcp_needs_the_api_key(mcp_client):
    assert mcp_client.post("/mcp", json=INIT, headers=HEADERS).status_code == 401
    wrong = {**HEADERS, "Authorization": "Bearer nope"}
    assert mcp_client.post("/mcp", json=INIT, headers=wrong).status_code == 401


def test_mcp_works_on_the_function_url_with_the_key(mcp_client):
    ok = {**HEADERS, "Authorization": f"Bearer {KEY}"}
    reply = mcp_client.post("/mcp", json=INIT, headers=ok)
    assert reply.status_code == 200
    assert reply.json()["result"]["serverInfo"]["name"] == "homework-helper"


def test_refuses_to_serve_without_a_key():
    with pytest.raises(RuntimeError):
        cloud.create_mcp_app("")


def test_reminder_handler_queues_each_reminder_once(monkeypatch):
    work = [due_in(2, id=1), due_in(20, id=2), due_in(100, id=3)]

    class FakeCanvas:
        def assignments(self):
            return work
    monkeypatch.setattr(cloud.Canvas, "from_env", classmethod(lambda cls: FakeCanvas()))
    table = FakeTable()

    assert cloud.reminder_handler(tbl=table) == {"new_reminders": 2}
    assert cloud.reminder_handler(tbl=table) == {"new_reminders": 0}

    inbox = store.Inbox(table)
    assert inbox.count() == 2
    heard = inbox.take()
    assert heard[0].startswith("Heads up: HW 1") and "HW 2" in heard[1]
    assert inbox.count() == 0
    assert all(item["expires"] > datetime.now().timestamp()
               for (pk, _), item in table.items.items() if pk != "name")


def test_reminder_handler_keeps_spoken_names(monkeypatch):
    work = [due_in(2, id=1)]

    class FakeCanvas:
        def assignments(self):
            return work
    monkeypatch.setattr(cloud.Canvas, "from_env", classmethod(lambda cls: FakeCanvas()))
    monkeypatch.setattr(names, "ask_bedrock", lambda titles: {"HW 1": "the first homework"})
    table = FakeTable()
    cloud.reminder_handler(tbl=table)
    assert store.Inbox(table).take()[0].startswith("Heads up: the first homework")
    assert store.DynamoNames(table).load() == {"HW 1": "the first homework"}


def test_alexa_app_reads_the_cloud_inbox(monkeypatch):
    table = FakeTable()
    store.Inbox(table).add([("1:x:soon", "Heads up: HW 1 is due soon.")],
                           datetime.now(timezone.utc))
    monkeypatch.setattr(mcp_server, "load_work", lambda: pytest.fail("shouldn't check Canvas"))
    assistant = alexa_app.Assistant(inbox=store.Inbox(table))
    with TestClient(alexa_app.create_app(assistant), base_url="http://127.0.0.1:8000") as client:
        assert client.get("/api/notifications").json() == {"count": 1}
        assert client.post("/api/notifications").json() == {
            "notifications": ["Heads up: HW 1 is due soon."]}
        assert client.get("/api/notifications").json() == {"count": 0}
