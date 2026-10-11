"""Loads the Homework Helper Agent Skill (skills/homework-helper/SKILL.md).

The skill follows the open Agent Skills standard, so any compatible agent can
load it from the folder directly. This loader is for agents we build
ourselves, like the simulated Alexa+ app: it validates the skill and returns
the instructions to give the agent.
"""

from pathlib import Path

from skills_ref import read_properties, validate

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "homework-helper"


def load_skill(skill_dir: Path = SKILL_DIR) -> str:
    """The skill's instructions, with its example conversations appended."""
    problems = validate(skill_dir)
    if problems:
        raise ValueError(f"Invalid skill in {skill_dir}: {'; '.join(problems)}")
    props = read_properties(skill_dir)
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    body = text.split("---", 2)[2].strip()          # drop the frontmatter
    examples = (skill_dir / "references" / "examples.md").read_text(encoding="utf-8")
    return f"{props.description}\n\n{body}\n\n{examples}"
