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
- **"Plan my week"**: a timed study schedule for the week. Every
  assignment lands on a day before it's due, within a daily study-time
  budget. Quizzes get study time the day before, exams get two sessions,
  and long lab reports are split across days. It fits around the student's
  Google Calendar, and the full schedule appears on screen. ✅ Built
- **Change the plan by talking**: "squeeze in my gym time from 7 to 8",
  "I go to bed at 10", "I get home at 5". The schedule reworks itself
  around it and remembers it for next time, including when it puts study
  sessions on your calendar. ✅ Built
- **"I finished Quiz 2"**: marks work done in Canvas by voice, so it drops
  off the list and reminders. If it's unclear which assignment you mean, it
  asks. ✅ Built
- **Sounds like a person**: Amazon Bedrock turns long Canvas titles into
  what a student would say ("STEM Fluency 3", "the free fall pre-lab"), and
  it only mentions how long things take when you ask. ✅ Built
- **Study sessions on Google Calendar**: turns the week plan into time
  blocks, fitted into free time around practice, class, and other events,
  each linking back to the assignment in Canvas. Re-planning replaces the
  old sessions and never touches the student's own events. ✅ Built
- **Proactive reminders**: speaks up about work that isn't submitted the day
  before it's due, again a few hours before, and once if it goes overdue.
  It never repeats a reminder, and starts over if a teacher moves the due
  date. ✅ Built
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
- **MCP server** (official MCP Python SDK, Streamable HTTP, spec 2025-11-25
  and newer) exposes six tools Alexa+ can call: what to work on, plan my
  week, upcoming assignments, reminders, mark work done, and add study sessions to the
  calendar. Every tool returns a ready-to-speak `say` answer plus structured
  details, so the agent can read the answer as-is and still handle
  follow-ups like "when is that due?". Read-only tools are marked read-only,
  so an agent knows only the calendar and mark-done tools change anything. ✅ Built
- **Agent Skill** (open `SKILL.md` standard) teaches the agent which tool
  fits each question, how to keep answers to about two sentences for
  listening, how to handle overdue work that may already be done on Pearson,
  and to change the calendar only when asked. It passes the standard's
  reference validator, and a test fails if the skill and the MCP server's
  tools ever drift apart. ✅ Built
- **Simulated Alexa+ web app**: an Echo-style light ring in the browser. You
  speak a question, an agent built with the **Strands Agents SDK** on
  **Amazon Bedrock** (Amazon Nova 2 Lite) follows the Agent Skill and calls
  the MCP server over Streamable HTTP, and the answer is spoken back. New
  reminders turn the ring yellow, like a real Alexa notification. If
  something fails, it says what's wrong out loud instead of going silent.
  It runs against the MCP server deployed on Lambda. ✅ Built
- **AWS:** Lambda hosts the MCP server, EventBridge Scheduler checks Canvas
  for reminders twice a day, DynamoDB holds the reminder inbox and spoken
  names, and Bedrock runs both the agent and the naming. One script deploys
  it all from a SAM template (details in the AWS Builder section). ✅ Built
- **Week planner**: places each assignment on the lightest day before it's
  due, adds study time before quizzes and exams, splits long work across
  days, then fits every session into free time around the student's Google
  Calendar. ✅ Built
- Python, with 90 automated tests (pytest) covering the Canvas parsing,
  planner, reminders, MCP tools, cloud handlers, and the web app.

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

**Canvas titles are written to be read, not heard.** "Pre-lab for
Acceleration of a Freely Falling Object" is fine on a page and painful out
loud. Telling the agent to shorten titles wasn't enough: Nova 2 Lite mostly
read the server's answer word for word, and reminders don't pass through the
agent at all. So the server asks Bedrock once per new title for the name a
student would say ("free fall acceleration pre-lab"), keeps it in DynamoDB,
and uses it everywhere. If two names would sound alike, both fall back to
their longer titles, and if Bedrock is unreachable, simple rules trim the
title instead.

**A new AWS account couldn't call Bedrock.** The models were listed as
available, but every call failed: first "account being verified", then a
"tokens per day" quota of 0 that the console marked not adjustable. It took
a Support case and a day of waiting. I kept building with a stand-in agent
so nothing else stalled, and made the app say quota and sign-in problems out
loud instead of hanging (Strands' default retries had kept one request
silent for over two minutes).

**Packaging for Lambda from Windows.** pip's cross-platform install still
tried to install Windows-only packages for Linux, and `cloudformation
package` silently ignored `CodeUri` under `Globals` and uploaded my whole
project folder, `.venv` included, until the stack failed on size. I switched
to `uv` with a Linux target and wrote a small deploy script that builds the
zip itself.

**A voice answer can't hold a week.** Reading out twelve study sessions is
too much to remember. The spoken answer now says where to start and what's
on today, and the full timed schedule appears on screen as a card, like an
Echo Show. Asking "what about Wednesday?" answers from the same plan.

## Accomplishments that we're proud of

**[DRAFT: keep the ones that mean the most to you]**

- **It runs on my real homework.** Every feature was tested against my
  actual Physics course, which is how I found the Pearson duplicates and the
  deadline bugs that made-up test data would never have shown.
- **The full voice loop works in the cloud.** A spoken question goes to a
  Strands agent on Bedrock, which calls the MCP server on Lambda, which
  reads Canvas, and the answer is spoken back. Reminders arrive on their
  own from EventBridge Scheduler.
- **It plans for learning, not just finishing.** The week plan adds study
  time before quizzes, splits long lab reports, and fits around my
  calendar, instead of just listing due dates.

## What we learned

**[DRAFT]**
- How the Canvas planner API works, and why real data needs testing (my fake
  test data would never have shown the Pearson duplicates).
- **Designing tools for a voice agent.** Each MCP tool returns a
  ready-to-speak `say` plus structured details. The agent answers quickly,
  still handles follow-ups, and the web app draws cards from the same data.
- **Agents follow examples more than rules.** Removing time estimates from
  the example conversations in the Agent Skill mattered as much as the rule
  saying not to give them.
- **Strands hooks** let the app see every tool result, which is how the
  schedule reaches the screen without asking the model to repeat it.
- **Running an existing web app on Lambda** with the Lambda Web Adapter,
  scheduling in the student's time zone with EventBridge Scheduler, and
  keeping several kinds of record in one DynamoDB table with TTL clean-up.
- **New-account limits are real.** Check Bedrock quotas on day one, not the
  night before a demo.

## What's next for Homework Helper

**[DRAFT]**
- Connect to real Alexa+ when MCP integrations open beyond the preview program.
- Support for other learning platforms (Google Classroom, Schoology).
- Learn how long you actually take on each type of assignment to plan better
  (time estimates are rules based on the title for now).
- Let the student say how they study best ("I like to start early", "no
  homework on Fridays") and plan around it.

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

**[DRAFT]** Everything is defined in one AWS SAM template
(`template.yaml`) and deployed with `python deploy/deploy.py`, which only
needs the AWS CLI.

- **AWS Lambda (MCP server):** the Homework Helper MCP server runs as a
  normal Python web app inside Lambda through the AWS Lambda Web Adapter,
  served at a Lambda Function URL. Every request must carry a bearer API
  key. It reads Canvas, plans, marks work done, and adds study sessions to
  Google Calendar.
- **AWS Lambda (reminders) + Amazon EventBridge Scheduler:** a second
  function runs at 7 AM and 7 PM in the student's own time zone
  (`ScheduleExpressionTimezone`), checks Canvas for work due within a day,
  within three hours, or overdue, and queues each new reminder once.
- **Amazon DynamoDB:** one table, three kinds of record told apart by
  partition key: reminders already sent, reminders waiting to be heard (the
  notifications that turn the ring yellow), and the spoken name for each
  assignment title. Sent reminders and notifications expire on their own
  with DynamoDB TTL.
- **Amazon Bedrock (Amazon Nova 2 Lite):** the model behind the Strands
  agent that answers the student, and, from inside both Lambda functions,
  the model that writes short spoken names for new assignments. It's called
  through the US cross-region inference profile.
- **AWS IAM:** one managed policy gives both functions only what they need:
  read and write on the one table, and `bedrock:InvokeModel` on the Nova
  inference profile.
- **AWS CloudFormation and Amazon S3:** the SAM template deploys as a
  CloudFormation stack; S3 holds the uploaded Lambda package.

### Product feedback

**[DRAFT: check the opinions are yours, especially "would use again"]**
Full details are in [FRICTION_LOG.md](../FRICTION_LOG.md).

**Amazon Bedrock (Amazon Nova 2 Lite)**
- *Used for:* the agent's reasoning and tool calls, and short spoken names
  for assignments.
- *Worked:* once access opened, the Converse API was simple. Nova 2 Lite
  was fast enough for voice and good at picking the right tool and
  rewriting titles.
- *Needs work:* onboarding for a new account. Calls failed with "account
  being verified", then a 0 tokens-per-day quota marked not adjustable,
  with nothing in the console saying why or how to get more. Fixing it took
  a Support case and a day. The model also tended to read tool output word
  for word even when told to shorten it.
- *Would use again:* **[YOU]**

**Strands Agents SDK**
- *Used for:* the agent that connects Bedrock to the MCP server.
- *Worked:* connecting to an MCP server over Streamable HTTP took a few
  lines, and hooks made it easy to see every tool result.
- *Needs work:* default retries kept a request silent for over two minutes
  on a daily quota error that waiting can't fix.
- *Would use again:* **[YOU]**

**AWS Lambda + Lambda Web Adapter**
- *Used for:* hosting the MCP server and the reminder check.
- *Worked:* the Web Adapter ran the existing web app unchanged, and Function
  URLs gave an HTTPS endpoint with no API Gateway setup.
- *Needs work:* building a Linux package on Windows. The documented `pip
  --platform` command still tries to install Windows-only packages.
- *Would use again:* **[YOU]**

**Amazon EventBridge Scheduler**
- *Used for:* reminder checks every morning and evening.
- *Worked:* schedules in the student's own time zone, set in one line of the
  template. No problems.
- *Would use again:* **[YOU]**

**Amazon DynamoDB**
- *Used for:* the reminder inbox, reminders already sent, and spoken names.
- *Worked:* one on-demand table with TTL covered everything, with no
  capacity planning.
- *Would use again:* **[YOU]**

**AWS CLI, AWS SAM template format, CloudFormation**
- *Used for:* sign-in (`aws login`) and deployment.
- *Worked:* `aws login` is much easier than access keys, and SAM kept the
  template short.
- *Needs work:* `aws login` credentials don't work from Python until you
  install `botocore[crt]`, and `cloudformation package` ignores `CodeUri`
  under `Globals` and quietly uploads the whole folder instead.
- *Would use again:* **[YOU]**

**Alexa+ (MCP integration) and the Agent Skills standard**
- *Used for:* the target platform. The MCP server and Agent Skill are built
  for Alexa+; the web app simulates the device because MCP integrations are
  still in a preview program.
- *Needs work:* a way for hackathon builders to test a real Alexa+
  connection would make the last step possible.

### Feature requests (optional)

**[DRAFT]**
- **Alexa+:** let developers connect their own MCP server to a test device,
  even with limits, so projects like this can run on a real Echo.
- **Amazon Bedrock:** give new accounts a small starting quota that works
  for a hello-world, and say "new-account quota" in the error with a link
  to request more.
- **Strands Agents:** don't retry errors that can't succeed soon (like a
  daily quota), and log retries by default so a hang is visible.
- **AWS CLI:** make `cloudformation package` understand SAM `Globals`, and
  include `botocore[crt]` so `aws login` works from Python out of the box.

### Demo video

**[TODO]** Script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Under 3 minutes, public
on YouTube, in English. Paste the link here once it's uploaded.
