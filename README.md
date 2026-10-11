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
- [ ] "What should I work on?": prioritize by due date, points, and time available
- [ ] "Plan my week": spread assignments across the week
- [ ] Add study sessions to Google Calendar
- [ ] Proactive reminders for work due soon that isn't submitted

**Alexa+ integration**

- [ ] **MCP server** (spec 2025-11-25, Streamable HTTP) exposing the planner as tools Alexa+ can call
- [ ] **Simulated Alexa+ web app**: speak a question, an agent calls the MCP server, and the answer is spoken back

**AWS**

- [ ] **Amazon Bedrock**: the AI model behind the simulated Alexa+ agent, and estimates of how long each assignment will take
- [ ] **Strands Agents SDK**: connects the Bedrock agent to the MCP server
- [ ] **AWS Lambda**: hosts the MCP server in the cloud
- [ ] **Amazon EventBridge Scheduler**: checks Canvas every morning and evening to trigger reminders
- [ ] **Amazon DynamoDB**: stores the week plan, settings, and which reminders were already sent

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

Run the tests with `pytest`.

## License

MIT
