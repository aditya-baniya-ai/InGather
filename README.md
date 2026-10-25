# ingather.

**Less scrolling. More together.** AI handles the coordination. Humans choose the connection.

InGather is an Instagram-inspired, privacy-first web app for HackTX 2026 (Meta track: *Bringing people closer together with AI*). You privately describe something you want to do, like "I'm at a conference in Philadelphia Jan 17–19 and free after 5pm". A **Meta Muse Spark** agent then finds compatible people who opted in, checks that the whole group has free time in common, and proposes a small group at a public place. It replans when you pass on someone or an invitee declines. Nobody is contacted until you approve, and nothing is confirmed until everyone does.

> Independent prototype. Not affiliated with or endorsed by Instagram or Meta. All demo people are fictional, and "verification" in the demo is simulated: no ID is checked.

## Run it (one command)

```bash
cp .env.example .env        # then put your MODEL_API_KEY in .env
docker compose up --build   # http://localhost:8000
```

On startup the container runs the database migrations. When `DEMO_MODE=true` it also loads 11 fictional demo accounts. On the sign-in page, use **Continue as Alice** (password `demo-password` for any `<name>@ingather.example`).

To reset the demo data: `docker compose down -v && docker compose up`.

Without `MODEL_API_KEY` the app still works in a clearly labeled **offline rules-based mode**, which is never presented as Muse Spark.

## Meta AI in the product

| Model | Where |
|---|---|
| `muse-spark-1.3`: **agent orchestra** (Responses API, tool calling, structured output) | A team of separate Muse Spark agents, each with its own instructions and only its own tools. **Matchmaker** finds compatible people. **Scheduler** (finds a time the whole group has free) and **Planner** (picks the activity, a public venue and an icebreaker) run in parallel. **Reviewer** approves each agent's work or sends it back once, and it also runs hard server checks the model can't override. The conductor proposes the group only after approval. The orchestra replans when you pass on someone or an invitee declines. Every timeline entry marked as a tool call is a real backend execution. |
| `muse-spark-1.3`: **Intake agent** | "Describe it" mode on Create Plan: it turns a sentence ("HackTX Oct 24–25 at UT Austin from 10am") into a pre-filled form you review. Nothing saves until you do. |
| `muse-image-1.0` | Plan cover images, generated only from activity, city and interests (no personal data). |
| `muse-voice-transcribe-1.0` | Speak your plan instead of typing it. |
| Muse connector (MCP at `/mcp`) | Lets your own Muse agent list your plans, run your Gather Agent and read your invitations, using a revocable token from Profile. It can't approve or confirm anything. |

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
- **The agent only reads, inside fixed limits.**
  - It sees opaque candidate handles and safe preview fields. It never sees other people's schedules, goal text, emails or venues.
  - Its toolbox only accepts candidates its own earlier search returned, re-checks exclusions and blocks, allows only public venue types, and requires a time inside a window the whole group has free.
  - Profile text is treated as untrusted data, never as instructions.
- **Human consent at every step.**
  - The owner approves invitations for an exact roster and proposal version.
  - Each recipient accepts or declines on their own; a decline is private, and so is a pass.
  - Any change to time, venue or roster resets everyone's final confirmation.
- **Blocks work both ways.** Two blocked people never appear in each other's candidates, invitations or proposals.

## Develop

```bash
# backend (Python 3.12, uv)
cd backend && uv sync && uv run python -m app.seed && uv run uvicorn app.main:app --reload --port 8000
uv run pytest -q                                   # backend tests incl. attacker cases, agent orchestra, verification
uv run python ../scripts/smoke_test_meta.py        # live Meta API check (never prints the key)

# frontend (Vite dev server proxies /api to :8000)
cd frontend && npm install && npm run dev          # http://localhost:5173
npm test && npm run build
```

Layout: `backend/app/{api,services,ai}` (FastAPI routers, domain services, Muse integrations), `backend/migrations` (Alembic), `frontend/src/{pages,components,lib}`. Binding API: [docs/api-contract.md](docs/api-contract.md). Product spec: [INGATHER_CLAUDE_CODE_BUILD_SPEC.md](INGATHER_CLAUDE_CODE_BUILD_SPEC.md).

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

Claude Code (an orchestra of agents: backend, AI-orchestra, verification and frontend engineers, a reviewer engineer that approves or rejects each piece, plus a manager doing integration), design skills (taste-skill, impeccable, Emil Kowalski's skills), and Playwright and the built-in browser for end-to-end testing. Runtime stack: React + Vite + Tailwind, FastAPI + SQLAlchemy + Alembic, Postgres, and the Meta Model API.
