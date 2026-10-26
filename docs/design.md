# Week Planner: Working Design Document

*Status: draft, revision 14. Last updated: October 16, 2026.*

## 1. Vision
Week Planner promotes a sustainable **routine, wellness and health** for **busy students and people with demanding
corporate jobs**. They have little free time, fixed commitments and a lot of stress; the app finds the real gaps in
their calendar and fills them with a plan they can actually keep: movement, home cooking, rest, connection and small
wellness habits.

**Design principles**
1. Consistency over intensity: recurring habits go at the same time of day so they become routine anchors.
2. Realistic, not ambitious: the plan adapts to how busy the week is; fewer, shorter items when it is packed.
3. Protect sleep and recovery: workouts end at least an hour before the waking hours end, rest or lighter days
   between hard sessions, no more than 5 hours of planned activity in a day, time to wind down.
4. Small habits count: 10 to 60 minute "wellness" items (walk, stretch, breathing, journaling, evening wind-down)
   fit into the gaps between meetings and study blocks.
5. Nourishing, not restrictive: balanced recipes; no calorie, weight-loss or diet-culture language; no shaming.
6. Encouraging, low-pressure tone; general wellness suggestions only, never medical advice, and a nudge to see a
   professional for pain, illness or mental health concerns.

A personal-use web app that turns "here's what I want from my week" into a realistic plan that fits the
user's actual calendar. The user describes what they want (workouts, cooking, time with friends, errands,
rest). The app asks a few follow-up questions, reads their calendar (read-only), finds free time, and
proposes a plan with recipes, workout ideas and local suggestions. The user approves the plan and the app
exports it as an .ics file.

**Core principles:** the app never touches the user's calendar (read-only in, a file out); the user
approves everything; scheduling is checked by code, not trusted to a model.

## Look and feel
Calm, sleek and professional with a little warmth. A light sage-green canvas, white surfaces with hairline borders
and soft shadows, one confident green for actions, muted pastel tints and simple line icons to tell activities
apart, and a small jellyfish guide (Jelly) whose speech bubble explains each step. The stepper is a clean numbered
path. The screen is a **workspace**: the steps are a sidebar on the left and the user's week is the anchor on the right, visible the whole time (an empty week with a hint at first, then busy time once the calendar is read, then the proposed plan on top). A week picker sits above it. Clicking a plan card highlights it on the calendar and the other way round. On a phone the calendar sits below the steps. The calendar shows: the user's busy time is hatched, planned
items are coloured by type, items they untick turn dashed, and a line confirms nothing overlaps their busy time.
Gentle motion only (a drifting jellyfish, rising bubbles when the file is downloaded), switched off for people who
prefer reduced motion; a dark theme; strong text contrast; no third-party fonts or assets.

## 2. User flow
1. **Describe the week** with cascading choices. The user picks categories (workouts, cooking, friends and family, errands and chores, rest); each pick opens its own follow-ups one group at a time (for workouts: how many, what kind, how long, where; for cooking: how many meals, which meals, cuisines, time per meal; for the others: how many and what kind). Two optional free-text boxes cover "anything else to schedule" and "anything the planner should know". The choices become exact goals (with counts) for the planner.
   An optional "About your week" block asks how busy the week is (light, normal, packed) and up to three priorities (more energy, less stress, better sleep, consistency, fitness, time with people, focus). Wellness habits are a category of their own.
   For workouts the user can choose "A fitness class": how many of their workouts should be classes, a studio they already go to (typed) or something new, and class types. The schedule then uses real class times.
2. **Follow-up questions.** The agent asks 3 to 5 short questions (preferred times, diet and allergies,
   budget, how far they'll travel, neighborhood or city, equipment, energy level). Answers are
   structured and editable.
3. **Calendar.** The user uploads an .ics file or pastes a private iCal link (works with Google, Apple
   and Outlook). The app only reads it.
4. **Free time.** Code computes free windows for the week inside the user's waking hours.
5. **Proposed plan.** The agent places activities into free slots, each with details: a recipe for
   cooking, a workout idea for exercise, and local suggestions (restaurants, parks, gyms, events) with
   sources.
6. **Review and approve.** The user accepts, removes, edits or asks to regenerate items. Nothing is final
   until approved.
   Step 5 (Approve) first shows the week as a calendar: busy time from the calendar, the proposed items on top, and a check that nothing overlaps. Tapping an item shows its details, and unticking an item in the list updates the picture.
7. **Export.** The approved plan downloads as an .ics file to import into any calendar.

## Evidence-based benefits
Because the goal is health, wellness and energy, every workout, meal, wellness habit, rest block and social item can
explain **why it helps the user's priorities** (more energy, less stress, better sleep, consistency, fitness, time with
people, focus). The explanation is never invented. It uses a curated list of 35 exact quotes from NIH (MedlinePlus,
NHLBI, NIMH, NCCIH), the NHS, and Harvard's Nutrition Source, each shown with its source name, a link and the date
it was checked. Claims are filed under the goals their quote itself states; weaker inferences are labelled "Related
to your goal…". A claim appears on an item only if it genuinely applies to it (a whole-grain quote needs a whole grain in
the recipe, a yoga quote needs yoga). If nothing applies, nothing is claimed. A maintenance script re-downloads every
page to confirm each quote is still there.

## 3. Key design decisions
| Topic | Decision |
|-------|----------|
| Calendar input | .ics upload or private iCal link, read-only. No Google OAuth for now. |
| Calendar privacy | Only busy/free ranges go to the model. Titles, attendees and locations stay in the backend process and are not stored. |
| Scheduling | Done in code: parse (including repeating events and time zones), find free time, validate the plan. The model chooses activities, code enforces the calendar. |
| Model | `gpt-6-luna` only, via Portkey, behind `backend/lib/llm` with spend limits. |
| Role | The profile asks "I'm mostly a student / working professional / something else" and then role-specific follow-ups (students: what they study, class times, course load, where they live; professionals: where they work, hours, meeting load, commute; other: a short description of a typical week). The answers shape the interview questions and the planner's routine. |
| Accounts / storage | Accounts with login (argon2id passwords, httpOnly session cookie). Profile stored server-side per user: waking hours, week start, time zone, city, diet/allergies, limits. The in-progress plan lives in the browser. |
| Calendar link | The user may choose "remember". The link is stored encrypted, never shown again, and can be forgotten. Uploaded files are never stored. |
| Local suggestions | Agent web search plus page fetching, with sources and dates. No places API for now. |
| Output | An .ics file (VEVENTs for approved items only, with recipe or workout notes in the description). |

## 4. Components
- **Calendar reader** (`backend/lib/calendar`): parse .ics, expand recurrences for the planning week,
  normalise time zones, merge overlapping busy blocks. Link fetching has SSRF protections.
- **Free-time finder**: free windows = waking hours minus busy blocks minus buffers. Returns ranges only.
- **Interview agent**: reads the user's description and asks the follow-up questions.
- **Planner agent**: proposes activities for free windows. Output is typed (activity, start, end,
  details, sources).
- **Plan validator** (code): rejects overlaps, out-of-hours items, missing buffers and invented sources.
- **Suggestion tools**: web search and `fetch_page` (public pages only) for local ideas and recipes.
- **.ics exporter**: builds the file from approved items only.
- **LLM gateway** (`backend/lib/llm`): the only place a model client exists. Allowlist, size caps,
  daily cap, kill switch, usage records.

## 5. Safeguards
1. Read-only calendar; the app never modifies it.
2. Calendar privacy: ranges only to the model; the file or link is not stored; a link is a secret.
3. User approval before anything is exported.
4. Code validates every proposed item against the real calendar.
5. Web content is untrusted data; every suggestion shows a source and date.
6. No medical advice; respect stated injuries, diets and allergies.
7. Model spend limits and a kill switch; fail safely, never fall back to another model.
8. Input limits on text and uploads.

## 6. Data
Backend SQLite (git-ignored): `users` (name, email, username, argon2id hash), `sessions` (hash of the cookie token), `profiles` (waking hours, week start, time zone, city, diet notes, limits), `calendar_links` (encrypted private link, host name), `ai_usage` (day, feature, tokens, cost; no content). Browser holds the in-progress plan.

## 7. Build order
1. **Scaffold:** React + Vite front end, FastAPI backend, LLM gateway wrapper with limits, tests. (Phase 1, done Oct 16)
2. **Accounts and profile** (login, waking hours and other profile fields), then **calendar import** (.ics upload, private link, optionally remembered encrypted) and the **free-time finder**, with tests. (Phase 2, done Oct 16)
3. Describe the week and the follow-up question agent, plus a week picker for the calendar. (Phase 3, done Oct 16)
4. Plan proposal with recipes and workouts, plus the code-side validator. (Phase 4, done Oct 16)
5. Local suggestions from web search, with sources.
6. Review, approve and .ics export, with tests. (Phase 6, done Oct 16; Phase 5, local suggestions, is still open)

## 8. Open questions
- [x] Waking hours, week start and time zone are profile fields asked of each user (defaults 7:00 to 22:00, Monday, browser time zone).
- [ ] How many items per day is too many? (default caps)
- [ ] Should the description, answers and plans be saved between visits (browser storage or server) or start fresh each time? (Currently page memory only.)
- [ ] Time zone: always the browser's, or choosable?
- [ ] Hosting: local only, or reachable from a phone? (Accounts make hosting safer to consider, but HTTPS is required first.)

## 9. Change log
- Rev 1 (Oct 16, 2026): initial design and phase 1 scaffold.
- Rev 2 (Oct 16, 2026): added accounts and a per-user profile (waking hours etc.), and the option to remember the private calendar link (encrypted).
- Rev 3 (Oct 16, 2026): added the week picker (reads 6 weeks), step 1 (describe your week) and step 2 (interview agent with 3 to 5 validated follow-up questions). Only yes/no profile flags and waking hours go to the model.
- Rev 4 (Oct 16, 2026): added the planner (step 4). It receives the profile notes (user's choice) and the free windows; code validates every item against the calendar, waking hours, buffers and diet or allergy notes before anything is shown. Local suggestions, approval and export remain.
- Rev 5 (Oct 16, 2026): added step 5 (approve: tick the items to include) and step 6 (download the .ics), with server-side re-validation on export, and fixed planning so the past is never offered. Local suggestions (phase 5) remain.
- Rev 6 (Oct 16, 2026): step 1 is now cascading choices (workouts, cooking, friends and family, errands, rest, plus two optional text boxes) instead of one text box. The choices become exact goals and the question agent skips what they already answered. The planner assumes typical lengths for unscheduled extras (haircut, call).
- Rev 7 (Oct 16, 2026): "Propose a different plan" now takes notes on what to change (with quick-idea chips). A revision sends the change request, the current plan and the removed items to the planner, which revises instead of starting over; removed items don't come back and the same validation applies.
- Rev 8 (Oct 16, 2026): "A fitness class" workouts. The user names a studio or picks something new; a class-finder agent reads real schedule pages and code verifies each class before the planner may schedule it at its exact time, with a source link. Unreadable studios are reported with links. This starts phase 5 (local suggestions from web search) for classes only; restaurants, parks and events remain.
- Rev 9 (Oct 16, 2026): stated the purpose (routine, wellness and health for busy students and professionals) and built it in: a new `wellness` item kind and category, an optional "About your week" block (role, how busy, priorities), planner and interview prompts written around the principles, code rules that protect sleep (workouts end an hour before waking hours end) and prevent overload (5 hours of planned activity a day), and a plan summary showing the week's balance and routine anchors.
- Rev 10 (Oct 16, 2026): the profile now asks whether the user is a student, a working professional or something else, with follow-up questions that depend on the answer. The role summary goes to the interview agent (so it asks role-specific questions and never re-asks) and to the planner. The "I'm mostly" chips were removed from the weekly page. Profile data model: new `role` and `role_details` columns (older databases upgrade automatically).
- Rev 11 (Oct 16, 2026): new visual design: light green, calm pastel palette, cartoon-game styling, the Sprout mascot with step-by-step speech bubbles, an icon stepper, emoji category cards, colour-coded plan cards and a confetti finish. No behaviour or data changes.
- Rev 12 (Oct 16, 2026): restyled to be sleeker and more professional (hairline borders, one green, line icons, numbered stepper) and replaced the sprout mascot with a small jellyfish (Jelly). Added a week calendar visualisation to the approval step: busy time, proposed items, approval state and an overlap check. No data changes (it uses busy ranges already held in the page).
- Rev 13 (Oct 16, 2026): added "Why this helps" to each item: exact, verified quotes from NIH, NHS and Harvard pages linked to the user's priorities, chosen by the planner from a fixed evidence list and kept only if they truly apply (matching activity words, real ingredients). Inferences are labelled "Related to"; no evidence means no claim. The planner prompt limit rose from 8,000 to 16,000 characters to carry the list.
- Rev 14 (Oct 16, 2026): layout is now a workspace: choices in a sidebar, the week calendar as the always-visible anchor (week picker, busy time, proposed plan, approval state, overlap check, linked highlighting). No behaviour or data changes.
- Rev 15 (Oct 16, 2026): optional weekly reminder email (profile settings: day, time, address; SMTP; in-server scheduler; new `reminders` table). The email carries no calendar, plan or profile content.
- Rev 16 (Oct 16, 2026): dinner reservations (the user chooses reservation or walk-in; a short list of up to 5 restaurants with booking links is shown): a restaurant finder agent suggests real restaurants near the user and reads reservation times only where a page really shows them (code-verified); otherwise it links to the booking page. Never books. Same cache/validation pattern as classes.
- Rev 17 (Oct 16, 2026): cooking asks for ingredients to use (built into recipes, unused ones reported) and an optional grocery trip scheduled before the first cooked meal.
- Rev 18 (Oct 17, 2026): "Game or movie night" split into "Game night" and "Movie night"; movie night asks theater or stay in, then genre, and a movie finder suggests real movies in theaters or to watch at home (page-verified, no tickets bought).
- Rev 19 (Oct 17, 2026): "Meal out" and "Dinner reservation" merged into "Go out to eat" (asks breakfast, brunch, lunch or dinner, then reservation or walk-in); options that bundle alternatives now ask which one the user wants (coffee/tea/drinks, yoga/Pilates, etc.).
- Rev 20 (Oct 17, 2026): speed: call timeouts with one retry, web searches start early (prefetch) while the user answers questions, finder pages read in one step.
- Rev 21 (Oct 19, 2026): the calendar invite no longer includes "why this helps" (it stays in the app); workouts list specific exercises with sets, reps and rest, enforced in code.
- Rev 22 (Oct 25, 2026): fixes: a changed NHS quote corrected (35 of 35 verified); the calendar opens on next week when 2 or fewer days remain; class, restaurant and movie results moved from memory to a `search_cache` table so export survives a restart; email setup script and .env template.
- Rev 23 (Oct 25, 2026): removed the weekly reminder email feature entirely (code, settings, table and docs); the app sends no email.
- Rev 24 (Oct 25, 2026): forgotten password: enter your email, get a one-time 30-minute reset link (local mode: printed in the backend terminal, no email), set a new password, signed out everywhere.
