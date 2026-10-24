# InGather API contract (source of truth for frontend + backend + AI)

All endpoints are JSON under `/api`, except `/health`. Every endpoint except `/health`,
`/api/auth/*` requires `Authorization: Bearer <jwt>`. The actor is always derived from the
token. **Any resource the caller may not see returns `404 {"detail":"Not found"}`** (never 403
with details) so existence is not leaked. Validation errors are 422. Rate-limited: 429.

Datetimes are ISO-8601 UTC (`2027-01-17T22:00:00Z`); the frontend renders them in the plan's
IANA `timezone`. IDs are UUID strings.

## Auth — `app/api/auth.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/auth/register | `{email, password(min 8), display_name}` | `TokenOut` |
| POST | /api/auth/login | `{email, password}` | `TokenOut` (401 on bad creds) |
| GET | /api/auth/demo-accounts | – | `[{email, display_name, avatar_url, bio}]` **only when DEMO_MODE**, else 404 |
| POST | /api/auth/demo-login | `{email}` | `TokenOut`; only DEMO_MODE and only `is_demo` users |
| GET | /api/me | – | `MeOut` |
| PATCH | /api/me | `{display_name?, bio?, interests?, avatar_url?, discovery_paused?, group_only?}` | `MeOut`. Any other field (e.g. `verification`) is ignored. |

`TokenOut = {access_token, token_type:"bearer", user: MeOut}`

`MeOut = {id, email, display_name, avatar_url, bio, interests[], verification: "unverified"|"verified_demo"|"verified_live", is_demo, discovery_paused, group_only, can_discover: bool}`

`can_discover` = adult AND (verified_live OR (verified_demo AND DEMO_MODE)) AND not paused.

## Plans — `app/api/plans.py` (owner-only)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/plans | `PlanIn` | `PlanOut` (201) |
| GET | /api/plans | – | `[PlanOut]` mine only, newest first |
| GET | /api/plans/{id} | – | `PlanOut` (404 if not owner) |
| PATCH | /api/plans/{id} | partial `PlanIn` | `PlanOut` |
| POST | /api/plans/{id}/discovery | `{mode: "private_browse"|"mutual_discovery"|"paused", ai_consent?: bool}` | `PlanOut` (writes ConsentEvent) |
| DELETE | /api/plans/{id} | – | 204; status→cancelled, open proposals cancelled |

`PlanIn = {activity_type, title, goal_text, city, timezone, start_date, end_date, intent, interests[], group_min(2-4), group_max(2-4), group_only, preview_text?, windows: [{starts_at, ends_at}]}`
Validation: end_date ≥ start_date, ends_at > starts_at, 2 ≤ group_min ≤ group_max ≤ 4.

`PlanOut = PlanIn + {id, discovery_mode, status, cover_image_url, ai_consent: bool, created_at, latest_proposal_id|null, latest_run_id|null}`

## Agent — `app/api/agent.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/agent/runs | `{plan_id, goal?}` | `RunOut` (202). Requires plan.ai_consent (else 409 `{"detail":"ai_consent_required"}`) and `can_discover` (else 403 `{"detail":"not_eligible"}`). Runs in background. |
| GET | /api/agent/runs/{id} | – | `RunOut` (owner only) — frontend polls every 1s while `status=running` |

`RunOut = {id, plan_id, proposal_id|null, trigger, mode: "live"|"offline", status, summary|null, error|null, model|null, created_at, finished_at|null, events: [{seq, kind:"tool"|"model"|"system"|"error", tool_name|null, summary, created_at}]}`

`mode=offline` means no MODEL_API_KEY: deterministic rules-based matching; UI must label it "Rules-based (offline) — not Muse Spark".

## Proposals / invitations — `app/api/proposals.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/proposals/{id} | – | `ProposalOut`, shaped by viewer stage (below) |
| POST | /api/proposals/{id}/members/{user_id}/pass | `{feedback?: "prefer_same_event"|"prefer_group"|"different_activity"|"schedule"|null}` | `RunOut` — owner only; marks passed (candidate never notified) and starts a replan run |
| POST | /api/proposals/{id}/replan | `{feedback?}` | `RunOut` — owner asks for different people |
| POST | /api/proposals/{id}/approve-invitations | `{version, user_ids[]}` | `ProposalOut` — owner only; user_ids ⊆ current `suggested` members and version must match, else 409 |
| GET | /api/invitations | – | `[InvitationOut]` invitations addressed to me |
| POST | /api/proposals/{id}/respond | `{accept: bool}` | `ProposalOut` — invited member only; decline enqueues outbox `invitation_declined` → replan run |
| POST | /api/proposals/{id}/finalize | `{start_at?, end_at?, venue_label?, venue_category?}` | `ProposalOut` — owner; requires ≥1 accepted and no invites pending; bumps version, status→awaiting_final, clears confirmations |
| POST | /api/proposals/{id}/confirm | `{version}` | `ProposalOut` — owner or accepted member; when all confirmed for current version → `confirmed` (+ agent icebreaker message) |
| POST | /api/proposals/{id}/leave | – | `ProposalOut`/204 — member leaves; owner leaving = cancel |
| GET | /api/proposals/{id}/messages | – | `[MessageOut]` — confirmed proposals, current participants only |
| POST | /api/proposals/{id}/messages | `{body (1-1000)}` | `MessageOut` |

`ProposalOut = {id, plan_id, version, status, activity_title, explanation, start_at, end_at, timezone, city, venue_label, venue_category, venue_verified, icebreaker, viewer_role: "owner"|"invitee"|"member", members: [MemberOut], group_size, my_status, i_confirmed: bool}`

`MemberOut = {user_id, display_name, avatar_url, interests[], is_initiator, status, reason|null, confirmed: bool}`

Disclosure by viewer:
- **owner**: everything above, all non-`removed` members incl. `suggested`/`passed` with `reason`.
- **invitee (status invited)**: activity_title, city, date only (start_at date), group_size, initiator display_name. `members=[]`, no explanation of others, no venue.
- **member (accepted)**: members with status invited/accepted only (no suggested/passed/declined), no `reason`. Venue/time once `awaiting_final`.
- anyone else (incl. declined, passed, blocked): **404**.

`InvitationOut = {proposal_id, activity_title, city, date, group_size, from_display_name, from_avatar_url, status, expires_at}`

`MessageOut = {id, sender_id|null, sender_name ("Gather Agent" when null), body, created_at}`

## Safety — `app/api/safety.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/blocks | `{user_id}` | 201 — also removes the blocked user from my open proposals (and me from theirs) |
| GET | /api/blocks | – | `[{user_id, display_name}]` |
| DELETE | /api/blocks/{user_id} | – | 204 |
| POST | /api/reports | `{reason, details?, reported_user_id?, proposal_id?}` | 201 |

## AI extras — `app/ai/routes.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/voice/transcribe | multipart `audio` (WAV ≤ 10 min, ≤ 10 MB) | `{text}` via Muse Voice Transcribe; 503 `{"detail":"ai_unavailable"}` without key |
| POST | /api/plans/{id}/cover | – | `PlanOut` — owner; generates a cover via Muse Image from activity/city only (no personal data), saved under `/media/`; 503 without key |
| POST | /api/connector/tokens | – | `{token}` (shown once) for connecting the user's Muse agent |
| DELETE | /api/connector/tokens | – | 204 revoke all |

## Muse connector — `app/ai/connector.py`
`POST /mcp` — MCP (JSON-RPC 2.0, streamable HTTP, stateless) authenticated with a connector token
(`Authorization: Bearer igc_...`). Tools act **as that user only**: `list_my_plans`,
`get_plan_status`, `ask_gather_agent(plan_id)`, `list_my_invitations`. No tool can approve invites,
confirm meetups, or read others' data — those stay human clicks in the app.

## Service interfaces shared between engineers (Python)
```python
# app/services/policy.py
class Policy:                       # all authorization decisions live here
    def __init__(self, db: Session, settings: Settings): ...
    def can_discover(self, user: User) -> bool
    def own_plan(self, user: User, plan_id: UUID) -> Plan               # raises not_found()
    def blocked_between(self, a: UUID, b: UUID) -> bool
    def viewer_role(self, user: User, proposal: Proposal) -> str | None  # owner|invitee|member|None

# app/services/matching.py
@dataclass
class CandidatePreview: user_id: str; display_name: str; activity_type: str; shared_interests: list[str]; preview_text: str; intent: str
@dataclass
class GroupAvailability: possible: bool; windows: list[tuple[datetime, datetime]]; reason: str   # group-level only
class Matching:
    def __init__(self, db, settings): ...
    def find_candidates(self, plan: Plan, excluded: set[UUID], limit: int) -> list[CandidatePreview]
    def group_availability(self, plan: Plan, user_ids: list[UUID]) -> GroupAvailability
    def rank(self, plan: Plan, cands: list[CandidatePreview]) -> list[CandidatePreview]   # transparent baseline

# app/services/proposals.py
class Proposals:
    def __init__(self, db, settings): ...
    def save_agent_result(self, run: AgentRun, plan: Plan, picks: list[tuple[UUID, str]],
                          activity_title: str, explanation: str, start_at, end_at,
                          venue_label: str, venue_category: str, icebreaker: str | None) -> Proposal
        # re-validates every pick via Matching (eligible, not excluded, not blocked) and that
        # group_availability is possible; adds them as `suggested` to the plan's open proposal
        # (creating it if needed, bumping version). Raises ValueError on invalid picks.

# app/ai/orchestrator.py
class GatherAgent:
    def __init__(self, db, settings, client=None): ...      # client injectable for tests
    def run(self, run_id: UUID) -> None                     # executes AgentRun, writes events, saves proposal
def start_run(db, owner: User, plan: Plan, trigger: str, goal: str = "", excluded: set[UUID] = ()) -> AgentRun
def run_in_background(run_id: UUID) -> None                 # opens its own Session; used by BackgroundTasks / outbox
```
