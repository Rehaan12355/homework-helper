# Demo Video Script

Target: about **2:55** (the limit is 3:00). Public on YouTube, in English. The voice
demo comes first, inside the first 30 seconds.

What Alexa says depends on your Canvas that day, so the replies below are
examples. Record each voice moment a few times and keep the best take. Trim
the "Thinking…" pauses in editing so the video doesn't drag.

---

## Before you record

1. **Sign in to AWS:** `aws login`
2. **Pick your reminders source.** The ring should be yellow at the start.
   - *Cloud (matches the story you tell):* queue reminders with the
     scheduled function, then start the app against the cloud:
     ```powershell
     aws lambda invoke --function-name homework-helper-ReminderFunction-NiFMfXIHeUid --region us-west-2 out.json; type out.json
     $env:MCP_URL = "https://33gd5smsvikuxae2nqoeygdvlm0mtxmj.lambda-url.us-west-2.on.aws/mcp"
     $env:HOMEWORK_TABLE = "homework-helper-HomeworkTable-7YVF89AWCX8X"
     python -m homework_helper.alexa_app
     ```
     If `out.json` says `"new_reminders": 0`, there's nothing new to queue.
     Use the fallback.
   - *Fallback (always has reminders):* leave `HOMEWORK_TABLE` unset and add
     `--demo`. The agent still uses the cloud MCP server.
     ```powershell
     $env:MCP_URL = "https://33gd5smsvikuxae2nqoeygdvlm0mtxmj.lambda-url.us-west-2.on.aws/mcp"
     python -m homework_helper.alexa_app --demo
     ```
3. **Open http://127.0.0.1:8000 in Edge.** Edge has the "Aria Natural" voice,
   which sounds much more like Alexa than the default. Allow the microphone.
   Zoom to about 110% so the text is readable on YouTube.
4. **Pick the assignment you'll mark done.** Choose one you've really
   finished (it ticks "mark as done" in your real Canvas). If you use one
   you haven't, say "undo that" after the take.
5. **Open Google Calendar in a second tab**, on this week.
6. **Close notifications**, hide the bookmarks bar, and use a quiet room.
7. **Record** with Xbox Game Bar (Win + Alt + R) or OBS. Capture system
   audio so Alexa's voice is on the recording, and your mic for your
   questions.
8. **Have ready for later in the video:** the architecture diagram (below),
   the AWS console with the stack's resources, and `SKILL.md` open in your
   editor.

---

## The script

### 0:00–0:25 · Cold open: the voice demo

**Screen:** the app, full window, ring glowing yellow.

> **You (to the device):** Alexa, I have an hour free. What should I work on?

> **Alexa (example):** You can fit Quiz 2 and the free fall acceleration
> pre-lab. Start with Quiz 2, it's due tomorrow and worth 30 points.

**Then** a title card over the app, about 3 seconds:
**Homework Helper: a hands-free study planner for Alexa+**

> **Narration:** That's Homework Helper. It reads my real Canvas homework and
> decides what I should do next, hands-free.

*(about 20 words)*

### 0:25–0:45 · The problem

**Screen:** Canvas, clicking through course pages and the To Do list.
Then a publisher site (Pearson) if you have it.

> **Narration:** My homework is spread across Canvas and sites like Pearson.
> Finding what's due means opening a laptop and clicking through every
> course. A calendar tells you what's due, but not what to do right now.
> Canvas's old Alexa skill could only read out due dates, and it was shut
> down in 2021. Alexa+ can reason, so I built a planner that decides.

*(about 65 words)*

### 0:45–1:35 · Plan my week, and change it

**Screen:** back to the app.

> **You:** Alexa, can you plan out my week for these assignments?

> **Alexa (example):** Start today at 4 PM with the Motion Lab write-up.
> Today: the Motion Lab write-up, STEM Fluency 3 and the free fall pre-lab.
> After that, 8 more sessions through Thursday. The full plan is on your
> screen.

**Screen:** the schedule card. Scroll slowly; point with the cursor at a
purple "Study for Quiz 2" row, a "part 1 of 2" row, and a "Busy day" label.

> **Narration:** It doesn't just list due dates. It puts study time before
> each quiz, splits long lab reports across days, and fits everything into
> free time around my Google Calendar. And when life gets in the way, I just
> say so.

> **You:** Can you squeeze in my gym time from 7 to 8?

> **Alexa (example):** Got it, gym from 7 to 8. Start at 8 with studying for
> Quiz 2…

**Screen:** the card updates. Point at the grey "Gym · Your time" row with
the study sessions moved around it.

> **You:** Put it on my calendar.

**Screen:** switch to the Google Calendar tab and refresh. The study
sessions appear around your own events.

*(about 40 words narration)*

### 1:35–1:50 · Finishing work, by voice

> **You:** I finished the free fall pre-lab.

> **Alexa (example):** Done, I marked the free fall acceleration pre-lab as
> done in Canvas. Next up is Quiz 2.

> **Narration:** It marks work done right in Canvas, and if I'm vague, it
> asks which one I mean.

*(Optional, if time allows: "Mark STEM Fluency done" → "Which one, STEM
Fluency 3 or 4?")*

*(about 20 words narration)*

### 1:50–2:05 · Reminders

**Screen:** the yellow ring and the bell with its count.

> **You:** Alexa, what are my notifications?

> **Alexa (example):** You have 2 notifications. Reminder: STEM Fluency 3
> is due tonight at 11:59 PM and isn't submitted yet…

> **Narration:** Twice a day, Amazon EventBridge Scheduler checks Canvas in
> the cloud. When something's due soon and not submitted, the ring lights
> up, just like an Alexa notification.

*(about 30 words)*

### 2:05–2:40 · How it's built

**Screen:** the architecture diagram, then quick cuts: `SKILL.md`, the AWS
console (Lambda functions, DynamoDB table, EventBridge schedules).

> **Narration:** Homework Helper is an MCP server that Alexa+ can call, with
> an Agent Skill that teaches the agent to keep answers short enough to
> hear. Since Alexa+ MCP access is still in preview, I simulate the device:
> a Strands agent on Amazon Bedrock, using Nova 2 Lite, calls the server.
> The server runs on AWS Lambda. EventBridge Scheduler runs the reminder
> checks, and DynamoDB holds the reminder inbox. Bedrock also renames every
> assignment the way a student would say it, so "STEM Fluency Assignment 3"
> becomes "STEM Fluency 3".

*(about 85 words)*

### 2:40–2:55 · Close

**Screen:** back to the app with the schedule card, then an end card with
the GitHub link: **github.com/Rehaan12355/homework-helper**

> **Narration:** I built and tested all of it on my own real courses. Next,
> I want to connect it to a real Alexa+ device. Homework Helper: just ask
> what's next.

*(about 30 words)*

---

## Architecture diagram (for 2:05)

```
 You ── voice ──▶ Simulated Alexa+ (web app)
                          │
                          ▼
            Strands agent on Amazon Bedrock (Nova 2 Lite)
              + Homework Helper Agent Skill
                          │  MCP (Streamable HTTP)
                          ▼
            Homework Helper MCP server ── AWS Lambda
              │            │            │
              ▼            ▼            ▼
          Canvas API   Google       Amazon Bedrock
                       Calendar     (spoken names)

 Amazon EventBridge Scheduler (7 AM, 7 PM)
          │
          ▼
  Reminder check ── AWS Lambda ──▶ Amazon DynamoDB (reminder inbox,
                                    spoken names) ──▶ yellow ring
```

## Timing check

| Section | Start | Length |
|---|---|---|
| Cold open | 0:00 | 25 s |
| The problem | 0:25 | 20 s |
| Plan my week, and change it | 0:45 | 50 s |
| Finishing work | 1:35 | 15 s |
| Reminders | 1:50 | 15 s |
| How it's built | 2:05 | 35 s |
| Close | 2:40 | 15 s |
| **Total** | | **2:55** |

Narration is about 290 words. At a relaxed pace (about 150 words a minute)
that's just under 2 minutes, which leaves room for the voice moments. If a
take runs long, cut the optional "which one?" moment first, then shorten
"The problem".
