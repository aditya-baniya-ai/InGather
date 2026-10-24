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
| `muse-spark-1.3` (Responses API, tool calling) | Gather Agent. It runs a bounded loop over read-only tools (`get_my_plan_context` → `find_eligible_candidates` → `check_group_availability` → `propose_group`) and replans when you pass on someone or an invitee declines. Every timeline entry marked as a tool call is a real backend execution. |
| `muse-image-1.0` | Plan cover images, generated only from activity, city and interests (no personal data). |
| `muse-voice-transcribe-1.0` | Speak your plan instead of typing it. |
| Muse connector (MCP at `/mcp`) | Lets your own Muse agent list your plans, run your Gather Agent and read your invitations, using a revocable token from Profile. It can't approve or confirm anything. |

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
uv run pytest -q                                   # 77 tests incl. attacker cases and the agent loop
uv run python ../scripts/smoke_test_meta.py        # live Meta API check (never prints the key)

# frontend (Vite dev server proxies /api to :8000)
cd frontend && npm install && npm run dev          # http://localhost:5173
npm test && npm run build
```

Layout: `backend/app/{api,services,ai}` (FastAPI routers, domain services, Muse integrations), `backend/migrations` (Alembic), `frontend/src/{pages,components,lib}`. Binding API: [docs/api-contract.md](docs/api-contract.md). Product spec: [INGATHER_CLAUDE_CODE_BUILD_SPEC.md](INGATHER_CLAUDE_CODE_BUILD_SPEC.md).

## Deploy

The `Dockerfile` builds one image that serves both the React app and the API on `$PORT` (default 8000). Deploy it to any container host (Render, Fly.io, Railway, Cloud Run) with a managed Postgres and these settings:
- `DATABASE_URL=postgresql+psycopg://...`
- `MODEL_API_KEY`
- a long random `JWT_SECRET`
- `CORS_ORIGINS=https://your-domain`

Keep `DEMO_MODE=true` only for the judged demo. Real-world stranger meetups stay disabled (`ALLOW_REAL_WORLD_MEETUPS=false`) until real identity verification, moderation and a security review exist.

## Built with

Claude Code (a team of agents: backend, AI and frontend engineers, plus a manager doing integration), design skills (taste-skill, impeccable, Emil Kowalski's skills), and Playwright and the built-in browser for end-to-end testing. Runtime stack: React + Vite + Tailwind, FastAPI + SQLAlchemy + Alembic, Postgres, and the Meta Model API.
