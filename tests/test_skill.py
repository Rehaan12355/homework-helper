import asyncio
import re

from mcp import Client
from skills_ref import validate

from homework_helper import mcp_server
from homework_helper.skill import SKILL_DIR, load_skill


def test_skill_follows_the_agent_skills_standard():
    assert validate(SKILL_DIR) == []


def test_skill_only_names_tools_the_server_has():
    async def server_tools():
        async with Client(mcp_server.server) as client:
            return {t.name for t in (await client.list_tools()).tools}
    named = set(re.findall(r"`([a-z_]+)`", (SKILL_DIR / "SKILL.md").read_text()))
    tools = asyncio.run(server_tools())
    params = {"minutes_free", "minutes_per_day", "say", "name", "title",
              "assignment", "done", "minutes", "whole_week", "busy", "label", "start",
              "end", "days", "bedtime", "start_time", "remove"}
    assert named - params <= tools
    assert tools <= named, "every tool should be explained in the skill"


def test_loaded_instructions_skip_frontmatter_and_include_examples():
    text = load_skill()
    assert not text.startswith("---")
    assert "Pick the right tool" in text
    assert "Example conversations" in text
