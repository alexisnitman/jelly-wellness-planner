# Jelly Wellness Planner

A personal-use web app that helps busy students and working professionals build a weekly routine for **wellness and health**.
You describe your week with a few cascading choices, the app reads your calendar (read-only), finds your free time, and proposes a
plan: workouts, home-cooked meals, real fitness classes, meals out, movie nights and small wellness habits. You review and approve
it, and the app exports an `.ics` file you import into your own calendar. A small jellyfish, Jelly, guides you through it.

> Not medical advice. Workout and meal ideas are general suggestions. The "why this helps" notes quote public health pages
> (NIH, NHS, Harvard) word for word; the app never makes up health claims.

## How it works

1. **Describe your week** with choices (workouts, cooking, friends and family, errands, rest, wellness). Options that bundle
   alternatives ask which one you want.
2. **Answer a few follow-up questions** written by an AI agent.
3. **Add your calendar** (an `.ics` file or a private link). Only busy/free time ranges are used; event titles and details never
   reach the AI.
4. **Review the plan.** The AI proposes; **code decides**. Every item is checked against your free time, waking hours, buffers
   and diet/allergy notes before you see it.
5. **Approve and export** an `.ics` file. Nothing is added to any calendar unless you download and import it yourself.

Real-world suggestions (fitness classes, restaurants, movies) come from agents that read public web pages. Code keeps a result only
if it was found on a page that was actually downloaded and the time or title appears in that page's text. The app never books or
buys anything, and says plainly when it can't see availability.

## Stack

- **Frontend:** React + Vite + TypeScript, plain CSS (`frontend/`)
- **Backend:** FastAPI + PydanticAI (`backend/`), SQLite for accounts and profiles
- **AI:** `gpt-6-luna` only, called server-side through the Portkey gateway, behind one wrapper (`backend/lib/llm`) that enforces a
  model allowlist, size limits, timeouts, a daily spend cap and a kill switch

## Run it

You need Python 3.12+ and Node 20+, and a Portkey API key.

```bash
# backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env            # then put your PORTKEY_API_KEY in .env
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000

# frontend (in another terminal)
cd frontend && npm install && npm run dev      # http://localhost:5200
```

Tests (no network or model calls): `cd backend && ../.venv/bin/python -m unittest discover -s tests`

Forgotten passwords: there is no email sending. A reset link is printed in the backend terminal (local mode); see
`backend/reset_delivery.py` to plug in real email.

## Privacy and safety

- Passwords are hashed with argon2id; sessions are random tokens in an httpOnly cookie; every query is scoped to the signed-in user.
- A remembered calendar link is stored encrypted and never sent back to the browser. Uploaded files are never stored.
- Profile notes (city, diet and allergies, injuries) go to the planner model only, so plans respect them. Calendar contents never do.
- Keys stay on the server. The database, encryption key and `.env` are git-ignored.

Details of what is stored, what is sent to a model and what the limits are: [`output/harness.md`](output/harness.md).
Design and decisions: [`docs/design.md`](docs/design.md). Project rules: [`CLAUDE.md`](CLAUDE.md).

## Status

A personal project. Known limits include: booking sites and theater showtimes are usually unreadable (so you get links, not
confirmed tables or times), there is no HTTPS, email verification or account deletion yet, and plans live in page memory only
(reloading loses an unfinished plan).
