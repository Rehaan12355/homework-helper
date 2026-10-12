# Homework Helper

**Hands-free homework planner and reminder with Alexa+**

A study planner for students. Instead of just reading out due dates,
it decides what to work on, plans the week, and reminds you before you fall
behind, all hands-free.

> "Alexa, I have two hours free tonight. What should I work on?"
>
> "Start your Chapter 4 homework. It's worth 20 points and due Thursday.
> Save the STEM Fluency assignment for the weekend."

Built for the **Amazon Developer Hackathon 2026**: Alexa+ track, plus the
AWS Builder mini challenge.

## Why

Students juggle deadlines across many courses, and checking Canvas means
opening a laptop and clicking through every class. Voice makes it hands-free,
which also helps students with ADHD, dyslexia, or vision impairments.

## Roadmap

**Core features** (built and tested locally first)

- [x] Read courses and assignments from Canvas, including what's submitted
- [x] "What should I work on?": prioritize by due date, points, and time available
- [x] "Plan my week": spread assignments across the week
- [x] Add study sessions to Google Calendar
- [x] Proactive reminders for work due soon that isn't submitted

**Alexa+ integration**

- [x] **MCP server** (spec 2025-11-25, Streamable HTTP) exposing the planner as tools Alexa+ can call
- [x] **Agent Skill** (open `SKILL.md` standard): teaches the agent how to prioritize and how to answer briefly for voice
- [ ] **Simulated Alexa+ web app**: speak a question, an agent calls the MCP server, and the answer is spoken back (built and tested; waiting on Bedrock access for a live run)

**AWS**

- [ ] **Amazon Bedrock**: the AI model behind the simulated Alexa+ agent, and estimates of how long each assignment will take
- [ ] **Strands Agents SDK**: connects the Bedrock agent to the MCP server
- [x] **AWS Lambda**: hosts the MCP server in the cloud, behind a Function URL with an API key
- [x] **Amazon EventBridge Scheduler**: checks Canvas every morning and evening to trigger reminders
- [x] **Amazon DynamoDB**: stores which reminders were sent and which are waiting to be heard

**Submission** (due October 23, 2026, 12:00 PM PT)

- [ ] Demo video under 3 minutes (public on YouTube, in English)
- [ ] Project description on Devpost
- [ ] Product feedback for every tool used, including which AWS services and how
- [ ] Friction log (up to a 10% judging bonus)

## Architecture

```
Simulated Alexa+ (web app, voice)
        │
        ▼
Strands agent on Amazon Bedrock ──MCP (Streamable HTTP)──▶ Homework Helper MCP server (AWS Lambda)
                                                                 │        │        ▲
                                                                 ▼        ▼        │
                                                          Canvas API  DynamoDB  EventBridge Scheduler
                                                          Google Calendar API      (reminders)
```

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` with your Canvas address and an access token
(Canvas → Account → Settings → **+ New Access Token**), then check it can
read your work:

```
python -m homework_helper.canvas
```

Ask what to work on with 2 hours free:

```
python -m homework_helper.planner 120
```

Plan your week (optionally pass minutes per day, default 120):

```
python -m homework_helper.week
```

Put the plan on Google Calendar as study sessions. They're placed in free
time between `STUDY_START` (default 4 PM) and 11 PM, around your existing
events. Running it again replaces the old sessions instead of duplicating
them, and your own events are never changed. You'll need a Google Cloud
OAuth client (Desktop app) with the Calendar API enabled, saved as
`credentials.json`. The first run opens a browser to sign in.

```
python -m homework_helper.study_sessions          # preview
python -m homework_helper.study_sessions --sync   # add to calendar
```

Check for reminders: work due tomorrow, due within 3 hours, or overdue and
not submitted. Each reminder is said only once (add `--all` to see every
reminder that applies):

```
python -m homework_helper.reminders
```

### MCP server

Start the MCP server (Streamable HTTP at `http://127.0.0.1:8000/mcp`):

```
python -m homework_helper.mcp_server
```

It speaks MCP spec 2025-11-25 and newer, and offers these tools. Each one
returns `say`, a short answer ready to be spoken, plus the details behind it:

| Tool | What it does |
|---|---|
| `what_should_i_work_on` | Best work to do now; pass `minutes_free` to fill that time |
| `plan_my_week` | Spreads homework across the next 7 days |
| `list_assignments` | All unfinished work, most important first |
| `check_reminders` | Work due within a day, within 3 hours, or overdue |
| `add_study_sessions` | Puts the week plan on Google Calendar |

To try it in a browser, run `npx @modelcontextprotocol/inspector`, choose
**Streamable HTTP**, and connect to `http://127.0.0.1:8000/mcp`.

This local server only listens on your own computer and has no sign-in.
The cloud version (below) requires an API key.

### Agent Skill

[`skills/homework-helper/SKILL.md`](skills/homework-helper/SKILL.md)
follows the open [Agent Skills](https://agentskills.io) standard. It teaches
an agent which MCP tool fits each question, how to keep answers short enough
to listen to, how to handle overdue work Canvas can't see (like Pearson), and
to only change the calendar when asked. Any agent that supports Agent Skills
can load the folder; `homework_helper/skill.py` loads it for the simulated
Alexa+ agent. Check it against the standard with:

```
agentskills validate skills/homework-helper
```

### Simulated Alexa+

A web page that works like an Echo: tap the light ring (or press Space),
ask a question out loud, and hear the answer. Behind it, an agent built with
the **Strands Agents SDK** on **Amazon Bedrock** (Amazon Nova 2 Lite) follows
the Agent Skill and answers by calling the MCP server over Streamable HTTP.
New reminders turn the ring yellow, like an Alexa notification; ask "what
are my notifications?" to hear them.

Sign in to AWS first (`aws login`), then:

```
python -m homework_helper.alexa_app          # open http://127.0.0.1:8000
python -m homework_helper.alexa_app --demo   # reminders start fresh each run
```

Voice input needs Chrome or Edge; you can also type. Set `BEDROCK_MODEL_ID`
in `.env` to use a different model.

### Deploy to AWS

`template.yaml` (AWS SAM) sets up:

- **AWS Lambda** running the MCP server through the
  [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter),
  reachable at a Lambda Function URL. Every request must send
  `Authorization: Bearer <MCP_API_KEY>`.
- **Amazon EventBridge Scheduler** running a reminder check at 7 AM and 7 PM
  in the student's time zone.
- **Amazon DynamoDB** remembering which reminders were sent, and queuing new
  ones until they're heard (old records expire on their own).

You only need the AWS CLI and [uv](https://docs.astral.sh/uv/) (`pip install uv`),
not the SAM CLI. Sign in (`aws login`), then:

```
python deploy/deploy.py
```

It builds the Lambda package, deploys the stack, and prints `MCP_URL` and
`HOMEWORK_TABLE`. Your Canvas settings, time zone and Google sign-in
(`token.json`, so the cloud can add study sessions) come from `.env`. If
`.env` has no `MCP_API_KEY`, one is made and saved there. Add the two
printed values to `.env`, and the simulated Alexa+ app will use the cloud
MCP server and hear the reminders the scheduler found.

Run the tests with `pytest`.

## License

MIT
