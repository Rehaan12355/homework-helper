# Devpost Submission Draft

Working draft of the Devpost write-up. Update it as each feature is finished,
then copy each section into the matching field on Devpost.

Status markers (delete them before submitting):
- **[DRAFT]**: written, but check it's still accurate before submitting
- **[TODO]**: fill in once the feature is built
- **[YOU]**: needs your own words or experience

---

## Project name

Homework Helper

## Tagline

Hands-free homework planner and reminder with Alexa+

## Tracks

- **Primary track:** Alexa+
- **Mini challenge:** AWS Builder

---

## Inspiration

**[YOU]** _Tell your own story in 2–4 sentences: a time you almost missed (or
did miss) a deadline, and how checking Canvas fit into your day. Judges
respond to real moments. Example structure:_

> I take [classes] and my homework is spread across Canvas and publisher
> sites like Pearson. I'd already built a script that copies my Canvas
> deadlines into Google Calendar, but a calendar only tells you what's due.
> It doesn't tell you what to do *right now* when you sit down with an hour
> free. I wanted to just ask.

Canvas's own Alexa skill could read out due dates, but it was discontinued in
2021, and it could only look things up. Alexa+ can reason and take actions, so
I wanted to build what that older skill couldn't: a planner that decides.

## What it does

**[DRAFT]** Homework Helper is a voice-first study planner for students.

- **"What should I work on?"**: picks the best assignment for the time you
  have, weighing due dates, points, and anything overdue. ✅ Built
- **"Plan my week"**: spreads your assignments across the week and can add
  study sessions to Google Calendar. **[TODO]**
- **Reminders**: warns you about work due soon that you haven't submitted.
  **[TODO]**
- **Understands real Canvas data**: reads assignments, quizzes, and
  discussions across all courses, knows what you've already submitted, and
  handles homework from publisher sites like Pearson. ✅ Built

Because it's hands-free, it also helps students with ADHD, dyslexia, or
vision impairments, who are the ones most hurt by clicking through every
course page to piece together what's due.

## How we built it

**[DRAFT]**

- **Canvas planner API** fetches everything due across all courses in a
  single request (assignments, quizzes, discussions), including submission
  status, so answers come back fast enough for a voice conversation.
- **MCP server** (spec 2025-11-25, Streamable HTTP) exposes the planner as
  tools that Alexa+ can call. **[TODO]**
- **Agent Skill** (open `SKILL.md` standard) teaches the agent how to
  prioritize homework and how to answer briefly for voice. **[TODO]**
- **Simulated Alexa+ web app**: you speak a question, an agent built with the
  **Strands Agents SDK** on **Amazon Bedrock** calls the MCP server, and the
  answer is spoken back. **[TODO]**
- **AWS:** Lambda hosts the MCP server, EventBridge Scheduler triggers
  reminders, and DynamoDB stores plans and reminder history. **[TODO]**
- Python, with automated tests (pytest) for the Canvas logic.

## Challenges we ran into

**Real Canvas data is messy.** Testing against a real Physics course showed
that every Pearson Mastering homework appeared **twice**: the link the
teacher created (5 points, never marked submitted) and a second entry Pearson
creates when it sends the grade back (10 points, graded). Their due times
could even differ by an hour. Without handling this, Homework Helper would
have told me to redo homework I'd already finished. I wrote matching logic
that merges entries with the same course and title due within a day of each
other, and counts the homework done if either copy is.

**Canvas doesn't know about outside homework.** Canvas only marks work
"missing" if it's submitted inside Canvas, so overdue Pearson homework was
never flagged. Homework Helper checks the due date itself.

**Overdue work crowded out everything else.** My first version gave overdue
work double priority. On my real assignments, that meant a 5-point item five
days late beat a 30-point quiz due in three days, and two free hours went
entirely to old work. Overdue work is now scored like something due right
now, and fades the longer it's late (it's more likely closed, penalized, or
already done on Pearson). Work past its Canvas lock date is never suggested.

**[TODO]** _Add challenges from the MCP server, Bedrock, and AWS work. Copy
the best entries from FRICTION_LOG.md._

## Accomplishments that we're proud of

**[TODO]** _Pick 2–3 once more is built. Candidates: testing on real data
instead of made-up examples; the first time the voice demo answered
correctly; the planner explaining its choice._

## What we learned

**[DRAFT]**
- How the Canvas planner API works, and why real data needs testing (my fake
  test data would never have shown the Pearson duplicates).
- **[TODO]** MCP, Strands, Bedrock, and deploying to AWS.

## What's next for Homework Helper

**[DRAFT]**
- **"Alexa, I finished Quiz 2"**: let students mark work done by voice, for
  publisher homework Canvas can't see.
- Connect to real Alexa+ when MCP integrations open beyond the preview program.
- Support for other learning platforms (Google Classroom, Schoology).
- Learn how long you actually take on each type of assignment to plan better.

## Built with

**[DRAFT]** _Devpost's "Built with" tags:_
python, canvas-lms, mcp, amazon-alexa, amazon-bedrock, strands-agents,
aws-lambda, amazon-dynamodb, amazon-eventbridge, google-calendar

---

## Hackathon-specific fields

### Which existing work this builds on

**[DRAFT]** All code in this repository was written during the hackathon
window. The idea grew out of a separate personal script I wrote earlier that
copies Canvas deadlines into Google Calendar; no code from it was copied here.

### AWS Builder: which services and how

**[TODO]** _Describe each service and what it does, once deployed. Required
for the mini challenge._

### Product feedback

**[TODO]** _Required: for every tool, API, or SDK used: what you used it for,
what worked, what needs work, how onboarding felt, and whether you'd use it
again. Draw from FRICTION_LOG.md._

### Feature requests (optional)

**[TODO]**

### Demo video

**[TODO]** _Under 3 minutes, public on YouTube, in English. Lead with the
voice demo in the first 30 seconds._
