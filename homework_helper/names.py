"""Short, natural names for assignments, for speaking aloud.

Canvas titles are written to be read on a page: "STEM Fluency Assignment 3",
"Pre-lab for Acceleration of a Freely Falling Object". Spoken, they're a
mouthful. Amazon Bedrock rewrites each new title once the way a student
would say it ("STEM Fluency 3", "free fall pre-lab"), and the names are kept,
so each title costs one model call ever. If Bedrock can't be reached, simple
rules trim the title instead.

Names are kept in DynamoDB when HOMEWORK_TABLE is set (in the cloud),
otherwise in a local JSON file.

`find` works the other way: from what the student said ("the free fall
pre-lab") to the assignment they mean.
"""

import json
import os
import re
import sys

from homework_helper.canvas import Assignment

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
REGION = os.environ.get("AWS_REGION", "us-west-2")

PROMPT = """You name homework assignments for a voice assistant. For each \
Canvas title, give the short name a student would say out loud.

Rules:
- Two to five words. Keep what tells it apart: its number, chapter, or topic,
  and what kind of work it is (quiz, homework, pre-lab, lab report).
- Drop filler like "Assignment", "Informal Lab", dates, and anything in parentheses.
- Turn wordy topics into the plain phrase people use.
- Write it as it's spoken: spell out abbreviations a speech engine would
  read letter by letter ("CH 03 HW" -> "Chapter 3 homework"), but keep ones
  said as a word, like "STEM".
- Every name must be different, so two assignments never sound the same.

Examples:
"Motion Lab Informal Lab write-up" -> "Motion Lab write-up"
"STEM Fluency Assignment 3" -> "STEM Fluency 3"
"Pre-lab for Acceleration of a Freely Falling Object" -> "Free fall acceleration pre-lab"
"Quiz 2: MCQ (Displacement, Velocity, and Acceleration)" -> "Quiz 2"
"Quiz 1 (10/01/26)" -> "Quiz 1"
"CH 03 HW" -> "Chapter 3 homework"

Reply with only a JSON object mapping each title, exactly as given, to its \
short name.

Titles:
"""


def simple_name(title: str) -> str:
    """Rule-based fallback: drops parentheses, subtitles after a numbered
    heading ("Quiz 2: MCQ" -> "Quiz 2"), and the word "Assignment" before a
    number."""
    name = re.sub(r"\s*\([^)]*\)", "", title)
    head, colon, _ = name.partition(":")
    if colon and re.search(r"\d", head):
        name = head
    name = re.sub(r"\bAssignment\s+(?=\d)", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip() or title


def ask_bedrock(titles: list[str]) -> dict[str, str]:
    """Short names for the titles, from Amazon Bedrock."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=REGION)
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": PROMPT + json.dumps(titles, indent=1)}]}],
        inferenceConfig={"temperature": 0, "maxTokens": 60 * len(titles) + 100},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    found = json.loads(text[text.index("{"):text.rindex("}") + 1])
    # Only keep sensible answers; anything odd falls back to the rules.
    return {t: n.strip() for t, n in found.items()
            if t in titles and isinstance(n, str) and 0 < len(n.split()) <= 8}


class FileNames:
    """Names kept in a local JSON file."""

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("NAMES_FILE", "spoken_names.json")

    def load(self) -> dict[str, str]:
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save(self, new: dict[str, str]) -> None:
        names = self.load() | new
        with open(self.path, "w") as f:
            json.dump(names, f, indent=1)


def default_store():
    if os.environ.get("HOMEWORK_TABLE"):
        from homework_helper import store
        return store.DynamoNames(store.table())
    return FileNames()


def add_names(work: list[Assignment], names=None, namer=None) -> list[Assignment]:
    """Sets each assignment's spoken `name`, asking Bedrock about new titles."""
    names = names or default_store()
    namer = namer or ask_bedrock
    known = names.load()
    new = sorted({a.title for a in work} - known.keys())
    if new:
        try:
            found = namer(new)
        except Exception as err:      # never let naming break an answer
            print(f"Couldn't name assignments with Bedrock: {err!r}", file=sys.stderr)
            found = {}
        if found:
            names.save(found)
        known |= found
    for a in work:
        a.name = known.get(a.title) or simple_name(a.title)
    # Two different assignments must never sound alike.
    titles_by_name: dict[str, set[str]] = {}
    for a in work:
        titles_by_name.setdefault(a.name.lower(), set()).add(a.title)
    for a in work:
        if len(titles_by_name[a.name.lower()]) > 1:
            a.name = simple_name(a.title)
    return work


NUMBER_WORDS = {w: str(n) for n, w in enumerate(
    "zero one two three four five six seven eight nine ten".split())}
SPOKEN_FOR = {"hw": "homework", "ch": "chapter", "prelab": "pre lab",
              "prelecture": "pre lecture"}
FILLER = {"the", "a", "an", "my", "for", "of", "to", "and", "in", "on", "assignment"}


def _words(text: str) -> list[str]:
    text = " ".join(SPOKEN_FOR.get(w, w) for w in re.findall(r"[a-z]+|\d+", text.lower()))
    words = [NUMBER_WORDS.get(w, w) for w in text.split()]
    return [str(int(w)) if w.isdigit() else w for w in words if w not in FILLER]


def _same(said: str, word: str) -> bool:
    """Loose match, so "fall" finds "falling" and "labs" finds "lab".
    Numbers must match exactly."""
    if said.isdigit() or word.isdigit():
        return said == word
    return word.startswith(said[:5]) or said.startswith(word[:5])


def find(work: list[Assignment], said: str, done: bool = True) -> list[Assignment]:
    """The assignment the student means. Returns one match, several if it's
    unclear which they mean, or none.

    When marking work done, unfinished work is searched first; when undoing,
    only work they marked done."""
    exact = [a for a in work if said.strip().lower() in (a.title.lower(), a.name.lower())]
    if len(exact) == 1:
        return exact
    asked = _words(said)
    if not asked:
        return []

    def in_order(words: list[str]) -> bool:
        return any(all(_same(w, t) for w, t in zip(asked, words[i:]))
                   for i in range(len(words) - len(asked) + 1))

    def score(a: Assignment) -> tuple[float, bool]:
        title, name = _words(a.title), _words(a.name)
        found = sum(any(_same(w, t) for t in title + name) for w in asked) / len(asked)
        # Prefer words said in the same order: "motion lab" means the Motion
        # Lab, not the Intro to Motion pre-lab. Anything still tied is asked
        # about, rather than guessed.
        return found, in_order(title) or in_order(name)

    if done:
        pools = [[a for a in work if not a.done], work]
    else:
        pools = [[a for a in work if a.marked_done]]
    for pool in pools:
        scored = sorted(((score(a), a) for a in pool), key=lambda s: s[0], reverse=True)
        scored = [(s, a) for s, a in scored if s[0] >= 0.5]
        if scored:
            best = scored[0][0]
            return [a for s, a in scored if s == best][:3]
    return []


if __name__ == "__main__":
    # See what Bedrock calls your real assignments: python -m homework_helper.names
    from dotenv import load_dotenv
    from homework_helper.canvas import Canvas

    load_dotenv()
    work = Canvas.from_env().assignments()
    for t, n in ask_bedrock(sorted({a.title for a in work})).items():
        print(f"{t}  ->  {n}")
