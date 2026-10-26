# Jelly Wellness Planner

**App link:** not online. It is meant to be run **locally from a fresh clone** using the steps below (about 10 minutes).
**Report and code:** this repository.

A personal-use web app that helps busy students and working professionals build a weekly routine for **wellness and health**.
You describe your week with a few cascading choices, the app reads your calendar (read-only), finds your free time, and proposes a
plan: workouts, home-cooked meals, real fitness classes, meals out, movie nights and small wellness habits. You review and approve
the plan, and the app exports an `.ics` file that you import into your own calendar. A small jellyfish, Jelly, guides you through it.

> Not medical advice. Workout and meal ideas are general suggestions. The "why this helps" notes quote public health pages
> (NIH, NHS, Harvard) word for word; the app never makes up health claims.

**Contents:** [Try it (for graders)](#try-it-for-graders) · [What to try](#what-to-try) · [Troubleshooting](#troubleshooting) ·
[How it works](#how-it-works) · [Privacy and safety](#privacy-and-safety) · [Tests](#tests)

---

## Try it (for graders)

The app runs on **your own computer** (it is not hosted online). Setup takes about 10 minutes.

> **Teaching staff, your API key:** the app reads `PORTKEY_API_KEY` from a `.env` file, first in this repo's folder and then in the folder
> **above** it, so your usual `submissions/.env` is picked up automatically and you can skip step 2's key edit. (It uses `PORTKEY_API_KEY`
> only; `OPENAI_API_KEY` is not needed.)

You need:

- **Python 3.12 or newer** (check with `python3 --version`)
- **Node.js 20 or newer** (check with `node --version`)
- **A Portkey API key** (`PORTKEY_API_KEY`). The app calls its AI model through Portkey. If you have a `.env` with this key in the
  folder that contains this repo, you are done. Otherwise put the key in a `.env` file as shown in step 2. Keys are never stored in this repository.
- An internet connection (the AI and the web searches need it)

### 1. Get the code

```bash
git clone https://github.com/alexisnitman/jelly-wellness-planner.git
cd jelly-wellness-planner
```

### 2. Set up the backend (the Python part)

**Mac or Linux:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
copy .env.example .env
```

**Skip this paragraph if your `.env` is already in the folder above this repo.** Otherwise open the new file named `.env` in a text editor and paste your key after `PORTKEY_API_KEY=` (no quotes, no spaces), then save:

```
PORTKEY_API_KEY=paste-your-key-here
AI_ENABLED=true
```

### 3. Create the demo account (optional, saves you filling in the sign-up form)

```bash
cd backend
../.venv/bin/python scripts/create_demo_account.py        # Windows: ..\.venv\Scripts\python scripts\create_demo_account.py
```

This makes a throwaway account **on your computer only**:

| Username | Password |
|----------|----------|
| `demo` | `jelly-demo-2026` |

Its profile is already filled in (awake 7:00 to 22:30, New Haven CT, student), so you can go straight to planning. If you would rather
make your own account, skip this step and use "Create an account" in the app; it takes a minute.

### 4. Start the backend

Still inside the `backend` folder:

```bash
../.venv/bin/uvicorn main:app --port 8000                 # Windows: ..\.venv\Scripts\uvicorn main:app --port 8000
```

Leave this terminal window open. You should see `Application startup complete`.

### 5. Start the frontend (in a second terminal window)

```bash
cd frontend          # from the project folder
npm install
npm run dev
```

### 6. Open the app

Go to **http://localhost:5200** in your browser. At the bottom of the page you should see
"Backend connected · model gpt-6-luna · AI on". Log in with the demo account (or create one).

To stop the app, press `Ctrl+C` in each terminal window.

---

## What to try

A full run takes about 5 minutes. The app has six steps shown along the top of the sidebar: **Describe, Questions, Calendar, Plan,
Approve, Export**. Your week's calendar is always on the right.

1. **Describe (step 1).** Click the boxes for what you want this week, for example **Workouts** (pick 3, choose *Strength* and
   *Yoga or Pilates*) and **Cooking** (pick 3 dinners, choose a cuisine). Each choice opens follow-up questions underneath. Options that
   combine things, like "Yoga or Pilates" or "Coffee or drinks", ask which one you want. To see the real-world suggestions, also pick
   **Friends & family**, then **Movie night** (theater or stay in, then genre) and/or **Go out to eat** (which meal, reservation or
   walk-in, cuisine). Click **Next: a few more questions**.
2. **Questions (step 2).** An AI agent writes 3 to 5 follow-up questions about your week. Answer any you like (you can skip them) and click
   **Continue to my calendar**.
3. **Calendar (step 3).** Click **Upload a file** and choose [`docs/sample-calendar.ics`](docs/sample-calendar.ics) from this
   repository. It is a made-up student week (classes, a team meeting, a study group). Its busy time appears as grey hatched blocks on the right.
   (You can instead paste a private calendar link, or click *Skip my calendar* to plan around your waking hours only.)
   The calendar opens on **next week** when this week is almost over; use the arrows to pick a week. Then click **Plan this week around my calendar**.
4. **Plan (step 4).** Jelly swims while the plan is built (usually 20 to 60 seconds). Then look at:
   - the colored blocks on the calendar and the **"nothing overlaps your busy time"** check under it,
   - **click any card** to highlight it on the calendar,
   - **Why this helps** on a workout or meal: exact quotes from NIH, NHS or Harvard pages, each with a link to the source,
   - workouts with **sets, reps and rest**, and recipes with ingredients and steps,
   - the **restaurant and movie lists** (if you asked for them): real places and titles read from real web pages, with links. The app
     says plainly that **nothing is booked** and when it could not read availability.
   - **Change something or propose a different plan**: type a request such as "move workouts to the evening" and click *Update my plan*.
5. **Approve (step 5).** Click **Looks good: review and approve**, untick anything you don't want (it dims on the calendar), then click **Approve N items**.
6. **Export (step 6).** Click **Download .ics file**. Open the file in Apple Calendar, Google Calendar or Outlook to import it. Nothing is
   ever added to a calendar unless you do this yourself.

Things worth checking while you grade:

- **The AI proposes, code decides:** try asking for more than will fit (for example 7 workouts and 7 dinners in a packed week). Items that don't
  fit are listed as "couldn't fit" instead of being squeezed in or double-booked.
- **Real, not invented:** classes, restaurants and movies come only from pages the app really read. If it can't find or read any, it says so.
- **Privacy:** the page shows only busy/free time, never your event titles. The footer shows the AI spend against a $1 daily cap.
- **Profile tab:** set diet or allergy notes (for example "vegetarian") and plan again; recipes respect them. There is also a
  "Forgot your password?" link on the login page (see the note under Troubleshooting).

**Cost and limits.** A plan with no web searches costs well under a cent; a plan with a meal out and a movie costs about 7 cents,
nearly all of it web searches. The app stops AI calls once about $1 has been spent in a day. Results vary between runs because
they come from a live AI model and live web pages.

---

## Troubleshooting

| What you see | What to do |
|--------------|-----------|
| "Can't reach the backend" at the bottom of the page | The backend isn't running. Start it again (step 4) and refresh the page. |
| `Address already in use` when starting a server | Something else is using port 8000 (backend) or 5200 (frontend). Stop it, or close the old terminal windows and try again. |
| "AI features are turned off" or "paused" | Check that `.env` has your `PORTKEY_API_KEY` and `AI_ENABLED=true`, then restart the backend. "Paused: spending limit reached" means the $1 daily cap was hit; it resets the next day. |
| "The AI took too long to answer" | A slow moment on the AI side. Click the button again. |
| The restaurant or movie list is short or says it "couldn't read" pages | Expected sometimes: many booking and showtime sites hide their times from automated readers, so the app gives you links instead of pretending. |
| You forgot a password | Click **Forgot your password?** on the login page and enter the account's email. The app sends no email: the reset link is **printed in the terminal window where the backend is running**. Open that link in your browser (it works once, for 30 minutes). Or just run the demo script again to reset the demo account. |
| Want a clean start | Stop the backend, delete the folder `backend/data`, and start it again. |

---

## How it works

1. **Describe your week** with cascading choices (workouts, cooking, friends and family, errands, rest, wellness).
2. **Answer follow-up questions** written by an AI agent.
3. **Add your calendar** (an `.ics` file or a private link). Only busy/free time ranges are used; event titles and details never
   reach the AI.
4. **Review the plan.** The AI proposes; **code decides**. Every item is checked against your free time, waking hours, buffers
   and diet/allergy notes before you see it.
5. **Approve and export** an `.ics` file.

Real-world suggestions (fitness classes, restaurants, movies) come from agents that read public web pages. Code keeps a result only
if it was found on a page that was actually downloaded and the time or title appears in that page's text. The app never books or
buys anything, and says plainly when it can't see availability.

**Stack:** React + Vite + TypeScript (`frontend/`), FastAPI + PydanticAI with SQLite (`backend/`). The AI is `gpt-6-luna` only, called
server-side through the Portkey gateway behind one wrapper (`backend/lib/llm`) that enforces a model allowlist, size limits, timeouts,
a daily spend cap and a kill switch (`AI_ENABLED=false`).

## Privacy and safety

- Passwords are hashed with argon2id; sessions are random tokens in an httpOnly cookie; every query is scoped to the signed-in user.
- A remembered calendar link is stored encrypted and never sent back to the browser. Uploaded files are never stored.
- Profile notes (city, diet and allergies, injuries) go to the planner model only, so plans respect them. Calendar contents never do.
- Keys stay on the server. The database, encryption key and `.env` are git-ignored.

Details of what is stored, what is sent to a model and what the limits are: [`output/harness.md`](output/harness.md).
Design and decisions: [`docs/design.md`](docs/design.md). Project rules: [`CLAUDE.md`](CLAUDE.md).

## Tests

No network or AI calls are needed (about 3 seconds):

```bash
cd backend
../.venv/bin/python -m unittest discover -s tests          # Windows: ..\.venv\Scripts\python -m unittest discover -s tests
```

## Status

A personal project. Known limits include: booking sites and theater showtimes are usually unreadable (so you get links, not
confirmed tables or times), there is no hosting, HTTPS, email sending or email verification, and plans live in page memory only
(reloading loses an unfinished plan).
