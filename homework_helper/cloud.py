"""Homework Helper on AWS Lambda.

Two entry points, wired up in template.yaml:

  mcp_app           The MCP server, served by uvicorn inside Lambda through
                    the AWS Lambda Web Adapter, behind a Lambda Function URL.
                    Every request needs "Authorization: Bearer <MCP_API_KEY>".
  reminder_handler  Run by Amazon EventBridge Scheduler every morning and
                    evening. Checks Canvas and puts new reminders in the
                    DynamoDB inbox, where the Alexa+ app picks them up.

Try the MCP app locally:
  set MCP_API_KEY=anything && uvicorn homework_helper.cloud:mcp_app --port 8080
"""

import hmac
import json
import os
from datetime import datetime, timezone

from homework_helper import mcp_server, names, reminders, store
from homework_helper.canvas import Canvas


def _google_token_from_env() -> None:
    """Lambda's disk is read-only except /tmp, so the Google sign-in token
    comes in as GOOGLE_TOKEN_JSON and is written there."""
    token = os.environ.get("GOOGLE_TOKEN_JSON")
    if token:
        path = "/tmp/token.json"
        with open(path, "w") as f:
            f.write(token)
        os.environ["GOOGLE_TOKEN"] = path


class RequireApiKey:
    """ASGI middleware: rejects HTTP requests without the right bearer token."""

    def __init__(self, app, api_key: str):
        if not api_key:
            raise RuntimeError("Set MCP_API_KEY before serving the MCP server publicly.")
        self.app = app
        self.expected = f"Bearer {api_key}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            sent = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(sent, self.expected):
                body = json.dumps({"error": "unauthorized"}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_mcp_app(api_key: str | None = None):
    # host="0.0.0.0" turns off the localhost-only Host check: the Function
    # URL's own hostname has to be accepted, and the API key guards access.
    app = mcp_server.server.streamable_http_app(stateless_http=True, json_response=True,
                                                host="0.0.0.0")
    return RequireApiKey(app, api_key if api_key is not None else os.environ.get("MCP_API_KEY", ""))


def reminder_handler(event=None, context=None, tbl=None) -> dict:
    """Checks Canvas for new reminders and adds them to the inbox."""
    tbl = tbl or store.table()
    now = datetime.now(timezone.utc)
    work = names.add_names(Canvas.from_env().assignments(), store.DynamoNames(tbl))
    new = reminders.check(work, store.DynamoSentLog(tbl), now)
    store.Inbox(tbl).add([(r.key, r.text) for r in new], now)
    print(f"{len(new)} new reminder(s)")
    return {"new_reminders": len(new)}


if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    _google_token_from_env()
mcp_app = create_mcp_app() if os.environ.get("MCP_API_KEY") else None
