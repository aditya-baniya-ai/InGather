# ingather.

**Less scrolling. More together.** AI handles the coordination. Humans choose the connection.

InGather is an Instagram-inspired, privacy-first web app for HackTX 2026 (Meta track: *Bringing people closer together with AI*). You privately describe something you want to do, like "I'm at a conference in Philadelphia Jan 17–19 and free after 5pm". The **InGather matcher**, a machine-learning model trained on real Meetup.com group data, finds compatible people who opted in. Plain server code then checks that the whole group has free time in common and proposes a small group at a public place. It replans when you pass on someone or an invitee declines. Nobody is contacted until you approve, and nothing is confirmed until everyone does.

> Independent prototype. Not affiliated with or endorsed by Instagram or Meta. All demo people are fictional, and "verification" in the demo is simulated: no ID is checked.

## Run it (one command)

```bash
cp .env.example .env        # then put your MODEL_API_KEY in .env
docker compose up --build   # http://localhost:8000
```

On startup the container runs the database migrations. When `DEMO_MODE=true` it also loads:
- 11 fictional demo accounts to sign in with. Use **Continue as Alice** (password `demo-password` for any `<name>@ingather.example`).
- **1,000 fictional Austin residents** with realistic names, an "about" text, interests and free times for the coming week.
- **150 open groups** among them that the ML matcher formed, each with one or two spots left. These fill the Home feed.

The first start takes about a minute for this; later starts only top up and move plans to the current week. Set `DEMO_SYNTHETIC_USERS=0` to skip it.

Optional, once, with your Muse key (results are stored, so you never need to run it again):
```bash
docker compose exec app python -m app.demo.enrich --all
```
- **`--venues`:** finds real Austin cafés, food halls and libraries with Muse Spark web search, keeping only results backed by a source page. Groups then meet at those places.
- **`--bios`:** rewrites the 1,000 generated "about" texts in natural, first-person voice.

To reset the demo data: `docker compose down -v && docker compose up`.

Matching never needs `MODEL_API_KEY`: it runs on the server's own model and costs no tokens. The key turns on the Muse features below, which work before and after matching.

## Meta AI in the product

| Model | Where |
|---|---|
| `muse-spark-1.3`: **Intake agent** | "Describe it" mode on Create Plan: it turns a sentence ("HackTX Oct 24–25 at UT Austin from 10am") into a pre-filled form you review. Nothing saves until you do. |
| `muse-spark-1.3` + web search: **venue agent** | Finds three real public places near the middle of a group for the group to vote on, and builds the Austin venue catalog (`app/demo/venues.py`). Only results backed by a source page count as verified. |
| `muse-spark-1.3`: **join helpers** | "Write it with Muse" drafts your intro when you ask to join a group, using your own profile. After the host accepts, Muse writes your welcome note. Without a key both use plain templates. |
| `muse-spark-1.3`: **icebreaker and demo bios** | The group chat's opening question once a meetup is confirmed, and the one-time rewrite of the demo people's "about" texts. |
| `muse-image-1.0` | Plan cover images, generated only from activity, city and interests (no personal data). |
| `muse-voice-transcribe-1.0` | Speak your plan instead of typing it. |
| Muse connector (MCP at `/mcp`) | Lets your own Muse agent list your plans, run your Gather Agent and read your invitations, using a revocable token from Profile. It can't approve or confirm anything. |

## Matching: the InGather matcher (ML, no LLM)

Every Gather run is one pass of server code around an ML model (`backend/app/services/gather.py`). Each step appears live in the timeline:

1. **Matcher.** Hard filters first: people who opted in, are verified adults, are in the same city on the same dates, are free when you are, aren't blocked and weren't passed. Then the model scores each person's fit with your plan.
2. **Scheduler.** It tries every allowed group among the 10 best fits. It keeps the one with the best mix of fit with you, fit between the people, and an hour or more of shared free time.
3. **Venue.** The nearest mapped public place of a fitting kind, or a generic public suggestion.
4. **Checks.** Public place, everyone free at that time, group size, nobody excluded or blocked. The proposal service then re-validates everything.

The model is gradient-boosted trees over 11 features: shared interests, similarity in a learned interest space, same activity, intent or event, and hours of shared time. Interests are embedded with vectors learned from 1.76M real Meetup members' topic lists, so "AI" and "machine learning" count as close.

The fit part is trained on 300k real join decisions from the public Meetup.com dataset (Liu et al., KDD 2012). On groups never seen in training:

| | AUC | Top-5 picks who really joined |
|---|---|---|
| Old hand-written rule (count shared interests) | 0.57 | 62% |
| InGather matcher | 0.67 | 72% |

Plan context (activity, intent, same event, free-time overlap) isn't in that dataset, so it is simulated on top. Those weights are assumptions until real InGather outcomes exist to retrain on. Details, the leakage check and how to retrain: [backend/ml/README.md](backend/ml/README.md).

Serving needs only numpy. The trees ship as JSON in `backend/app/ml/artifacts/`, so there are no pickle files.

## Home feed: groups with room for you

Home shows open groups that have one or two spots left, ranked for you by the matcher. It compares your interests and plans with the group's: the host's plan plus the interests of the people already in it. If you have a plan in that city, it also checks whether you're free then.

Each card shows the activity, the day and part of day, the kind of place, first names, the interests you share and a fit score. The exact time, the venue and full names are shared only once the host accepts you.

To join:
1. Press **Ask to join**.
2. Optionally add a note, or have Muse draft one from your profile.
3. The host sees your name, bio, interests and note, then accepts or declines. A decline is private, and that group stops appearing in your feed.

In `DEMO_MODE`, the fictional Austin hosts answer within a few seconds, based on the same fit score. Real hosts answer on their proposal page, where they can also turn **Let people ask to join** on or off.

## Account verification

New accounts start out unverified and can't use discovery until they verify, on `/verify`:
- **Demo verification** (`DEMO_MODE=true`): you confirm you're 18+ and get a badge labeled "verification simulated, no ID checked".
- **Stripe Identity**, a hosted ID check:
  1. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`.
  2. Run `stripe listen --forward-to localhost:8000/api/webhooks/stripe --events identity.verification_session.verified`.
  3. The signature-checked webhook marks the account `verified_live` and sets adulthood from the verified date of birth.
  4. In test mode the badge says it was not a real ID check.

Verification confirms identity. It does not mean someone is safe.

## Security model (enforced by the backend, not by prompts)

- **One place decides access.** Every access check goes through `backend/app/services/policy.py`. Anyone not allowed to see a plan, proposal, invitation or chat gets a uniform `404`, so its existence isn't revealed.
- **Matching stays on the server.**
  - Other people's schedules, goal text, emails and event locations never leave the matching service. The owner only sees display names, shared interests, a reason and group-level times.
  - No LLM reads anyone's profile text, so there's nothing to prompt-inject.
  - The engine only suggests. Fixed checks (public venue types, a time inside a window the whole group has free, exclusions and blocks) run before the proposal service re-validates every pick.
- **Human consent at every step.**
  - The owner approves invitations for an exact roster and proposal version.
  - Each recipient accepts or declines on their own; a decline is private, and so is a pass.
  - Any change to time, venue or roster resets everyone's final confirmation.
- **Blocks work both ways.** Two blocked people never appear in each other's candidates, invitations or proposals.

## Develop

```bash
# backend (Python 3.12, uv)
cd backend && uv sync && uv run python -m app.seed && uv run uvicorn app.main:app --reload --port 8000
uv run pytest -q                                   # backend tests incl. attacker cases, matcher, gather engine, verification
uv run python ../scripts/smoke_test_meta.py        # live Meta API check (never prints the key)
uv run python ml/fetch_data.py && uv run --group train python ml/train.py   # retrain the matcher (~5 min)

# frontend (Vite dev server proxies /api to :8000)
cd frontend && npm install && npm run dev          # http://localhost:5173
npm test && npm run build
```

Layout: `backend/app/{api,services,ml,ai}` (FastAPI routers, domain services, the matcher, Muse integrations), `backend/ml` (matcher training), `backend/migrations` (Alembic), `frontend/src/{pages,components,lib}`. Binding API: [docs/api-contract.md](docs/api-contract.md). Product spec: [INGATHER_CLAUDE_CODE_BUILD_SPEC.md](INGATHER_CLAUDE_CODE_BUILD_SPEC.md).

## Meetup maps and group chat

Add a public conference venue or street address in the plan or Gather Agent workspace. The server geocodes that location and searches OpenStreetMap for public cafés, restaurants, food halls and libraries within 1.5 km, sorted by straight-line distance. Only that public location and city go to the map providers. Results are cached for 30 minutes; set `VENUE_SEARCH_ENABLED=false` to disable lookup. Public providers may be unavailable, in which case the UI offers manual venue entry without inventing a map pin.

The organizer can choose a mapped place before final confirmation. Its map is shared with accepted participants during confirmation and remains available in chat. Changing the place resets confirmations. Once everyone confirms, the group chat appears automatically on the right on desktop and inline on smaller screens, with sender names and avatars. Messages refresh every three seconds. The circular Messages button opens a searchable inbox with All, Groups and People filters. After a meetup is fully confirmed, its members can message each other privately from the inbox, group avatars or confirmation roster. These connections persist after the meetup; blocking either person prevents access and sending in both directions. Direct conversations are separate from the group, and show the latest 200 messages.

## Deploy

The `Dockerfile` builds one image that serves both the React app and the API on `$PORT` (default 8000). Deploy it to any container host (Render, Fly.io, Railway, Cloud Run) with a managed Postgres and these settings:
- `DATABASE_URL=postgresql+psycopg://...`
- `MODEL_API_KEY`
- a long random `JWT_SECRET`
- `CORS_ORIGINS=https://your-domain`

Keep `DEMO_MODE=true` only for the judged demo. Real-world stranger meetups stay disabled (`ALLOW_REAL_WORLD_MEETUPS=false`) until real identity verification, moderation and a security review exist.

## Built with

Claude Code (an orchestra of agents: backend, AI-orchestra, verification and frontend engineers, a reviewer engineer that approves or rejects each piece, plus a manager doing integration), design skills (taste-skill, impeccable, Emil Kowalski's skills), and Playwright and the built-in browser for end-to-end testing. Runtime stack: React + Vite + Tailwind, FastAPI + SQLAlchemy + Alembic, Postgres, numpy for the matcher (trained with scikit-learn), and the Meta Model API.
