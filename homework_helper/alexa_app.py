"""Simulated Alexa+: talk to Homework Helper in a web page.

The page listens with the browser's speech recognition, sends what you said
to an AI agent (Strands Agents SDK on Amazon Bedrock), and speaks the reply.
The agent follows the Homework Helper Agent Skill and answers by calling the
MCP server over Streamable HTTP, the same way Alexa+ would.

New reminders light the ring yellow, like an Alexa notification. Ask
"what are my notifications?" to hear them.

Run it:  python -m homework_helper.alexa_app        then open http://127.0.0.1:8000
         python -m homework_helper.alexa_app --demo  (reminders start fresh each run)
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from homework_helper import mcp_server, reminders
from homework_helper.canvas import CanvasError
from homework_helper.skill import load_skill

load_dotenv(".env")

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))
# The agent reaches the MCP server over HTTP. By default that's the one this
# app serves at /mcp; point MCP_URL at the cloud server once it's deployed.
MCP_URL = os.environ.get("MCP_URL", f"http://{HOST}:{PORT}/mcp")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-west-2")
PAGE = Path(__file__).resolve().parent.parent / "web" / "alexa.html"

VOICE_RULES = (
    "\n\nYou are speaking through a simulated Alexa+ device. Reply in plain "
    "spoken sentences only: no markdown, lists, emoji, or URLs."
)


def build_agent():
    from botocore.config import Config
    from mcp.client.streamable_http import streamable_http_client
    from strands import Agent, ModelRetryStrategy
    from strands.models import BedrockModel
    from strands.tools.mcp import MCPClient

    homework_tools = MCPClient(lambda: streamable_http_client(MCP_URL))
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION,
                         temperature=0.3, max_tokens=400,
                         boto_client_config=Config(retries={"max_attempts": 2},
                                                   read_timeout=30))
    # A voice assistant shouldn't go quiet for minutes retrying: one quick
    # retry, then explain the problem out loud.
    retry = ModelRetryStrategy(max_attempts=2, initial_delay=1, max_delay=2)
    return Agent(model=model, tools=[homework_tools],
                 system_prompt=load_skill() + VOICE_RULES,
                 retry_strategy=retry, callback_handler=None)


class Assistant:
    """One conversation at a time, like a single Alexa device."""

    def __init__(self, reminder_log: reminders.SentLog):
        self.agent = None
        self.lock = threading.Lock()
        self.reminder_log = reminder_log
        self.notifications: list[str] = []

    def ask(self, text: str) -> str:
        with self.lock:
            if self.agent is None:
                self.agent = build_agent()
            return str(self.agent(text)).strip()

    def reset(self) -> None:
        with self.lock:
            self.agent = None

    def check_reminders(self) -> int:
        """Adds any new reminders to the notification queue."""
        new = reminders.check(mcp_server.load_work(), self.reminder_log)
        self.notifications += [r.text for r in new]
        return len(self.notifications)

    def read_notifications(self) -> list[str]:
        unread, self.notifications = self.notifications, []
        return unread


def friendly_error(err: Exception) -> str:
    text = str(err)
    if "being verified" in text:
        return "My AWS account is still being verified, so I can't think yet. Try again soon."
    if "tokens per day" in text or "Throttl" in text or "Too many" in text:
        return "I've hit my Amazon Bedrock usage limit for now. Try again a bit later."
    if "AccessDenied" in text or "not authorized" in text:
        return "I don't have access to the Bedrock model. Check model access in the AWS console."
    if any(k in text for k in ("ExpiredToken", "Unable to locate credentials", "token has expired")):
        return "My AWS sign-in has expired. Run aws login, then try again."
    if isinstance(err, CanvasError):
        return "I can't reach Canvas right now. Your access token may have expired."
    return "Sorry, something went wrong. Check the terminal for details."


def create_app(assistant: Assistant):
    app = mcp_server.server.streamable_http_app(stateless_http=True, json_response=True)

    async def page(request: Request):
        return FileResponse(PAGE)

    async def ask(request: Request):
        text = ((await request.json()).get("text") or "").strip()
        if not text:
            return JSONResponse({"reply": "I didn't catch that."})
        try:
            reply = await run_in_threadpool(assistant.ask, text)
        except Exception as err:          # shown in the terminal, spoken simply
            print(f"Agent error: {err!r}", file=sys.stderr)
            return JSONResponse({"reply": friendly_error(err), "error": True})
        return JSONResponse({"reply": reply})

    async def reset(request: Request):
        assistant.reset()
        return JSONResponse({"ok": True})

    async def notifications(request: Request):
        if request.method == "POST":
            return JSONResponse({"notifications": assistant.read_notifications()})
        try:
            count = await run_in_threadpool(assistant.check_reminders)
        except Exception as err:
            print(f"Reminder check failed: {err!r}", file=sys.stderr)
            count = len(assistant.notifications)
        return JSONResponse({"count": count})

    app.router.routes.extend([
        Route("/", page),
        Route("/api/ask", ask, methods=["POST"]),
        Route("/api/reset", reset, methods=["POST"]),
        Route("/api/notifications", notifications, methods=["GET", "POST"]),
    ])
    return app


if __name__ == "__main__":
    if "--demo" in sys.argv:
        log_path = os.path.join(tempfile.mkdtemp(), "reminders_sent.json")
    else:
        log_path = None
    app = create_app(Assistant(reminders.SentLog(log_path)))
    print(f"Simulated Alexa+ running at http://{HOST}:{PORT}  (model: {MODEL_ID})")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
