# Homework Helper

**Hands-free homework planner and reminder with Alexa+**

A study planner for students. Instead of just reading out due dates,
it decides what to work on, plans the week, and reminds you before you fall
behind, all hands-free.

> "Alexa, I have two hours free tonight. What should I work on?"
>
> "Start your Chapter 4 homework. It's worth 20 points and due Thursday.
> Save the STEM Fluency assignment for the weekend."

Built for the **Build, Ship, Shape: Amazon Developer Hackathon 2026**
(Alexa+ track).

## Why

Students juggle deadlines across many courses, and checking Canvas means
opening a laptop and clicking through every class. Voice makes it hands-free,
which also helps students with ADHD, dyslexia, or vision impairments.

## Roadmap

**Core features** (built and tested locally first)

- [ ] Read courses and assignments from Canvas, including what's submitted
- [ ] "What should I work on?": prioritize by due date, points, and time available
- [ ] "Plan my week": spread assignments across the week
- [ ] Add study sessions to Google Calendar
- [ ] Proactive reminders for work due soon that isn't submitted
- [ ] Alexa+ integration (MCP server) and voice demo

**Running on AWS**

- [ ] **AWS Lambda**: runs the code in the cloud whenever Alexa+ asks a question
- [ ] **Amazon EventBridge Scheduler**: checks Canvas every morning and evening to trigger reminders
- [ ] **Amazon DynamoDB**: stores the week plan, settings, and which reminders were already sent
- [ ] _Stretch:_ **Amazon Bedrock**: estimates how long each assignment will take from its description

## Architecture

```
Alexa+ ──▶ AWS Lambda (Homework Helper) ──▶ Canvas API
                 │        ▲                  Google Calendar API
                 ▼        │
           DynamoDB   EventBridge Scheduler (reminders)
```

## Setup

_Coming soon._
