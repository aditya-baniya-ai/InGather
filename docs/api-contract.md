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
| PATCH | /api/me | `{display_name?, bio?, interests?, avatar_url?, discovery_paused?, group_only?, home_area? (≤80, "" clears), gender?: woman\|man\|non_binary\|self_describe\|prefer_not_to_say\|"", gender_self? (≤40, kept only with self_describe), age_range?: 18-24\|25-34\|35-44\|45-54\|55+\|"", education? (≤120), work? (≤120), show_gender?, show_age?, show_background?}` | `MeOut`. Any other field (e.g. `verification`) is ignored; `""` clears an about-you field. Changing gender redraws a generated avatar (same seed) in the matching style; uploaded photos are untouched. |
| POST | /api/me/avatar | multipart `photo` | `MeOut`. JPEG/PNG/WebP decided by magic bytes (client type ignored), ≤3 MB (413), else 415 `unsupported_image`; stored as `/media/avatars/<random>.<ext>`. Rate-limited (5 / 5 min). |
| POST | /api/me/avatar/shuffle | – | `MeOut`. New random generated avatar (an uploaded photo is removed). |
| DELETE | /api/me/avatar | – | `MeOut`. Back to a generated avatar (keeps the previous seed if there was one). |
| GET | /api/avatars/{seed}.svg?g=woman\|man | – | Public, cacheable illustrated avatar; seed `[a-z0-9]{8,32}` else 404. Contains no user data. New users get one at sign-up; older accounts get one lazily on `GET /api/me`. |

`TokenOut = {access_token, token_type:"bearer", user: MeOut}`

`MeOut = {id, email, display_name, avatar_url, bio, interests[], verification: "unverified"|"verified_demo"|"verified_live", is_demo, discovery_paused, group_only, can_discover: bool, home_area|null, home_area_located: bool}` — `home_area` is private (owner only); its server-geocoded coordinates are rounded to 0.01° (~1 km) and never returned to anyone. Also owner-only: `gender, gender_self, age_range, education, work, show_gender, show_age, show_background` (switches default false) and `avatar_kind: generated|photo|other`

`can_discover` = adult AND (verified_live OR (verified_demo AND DEMO_MODE)) AND not paused.

## Plans — `app/api/plans.py` (owner-only)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/plans | `PlanIn` | `PlanOut` (201) |
| GET | /api/plans | – | `[PlanOut]` mine only, newest first |
| GET | /api/plans/{id} | – | `PlanOut` (404 if not owner) |
| GET | /api/plans/{id}/nearby | – | `{status, message, places[], origin?}` — owner only; public-event lookup, rate limited |
| PATCH | /api/plans/{id} | partial `PlanIn` | `PlanOut` |
| POST | /api/plans/{id}/discovery | `{mode: "private_browse"|"mutual_discovery"|"paused", ai_consent?: bool}` | `PlanOut` (writes ConsentEvent) |
| DELETE | /api/plans/{id} | – | 204; status→cancelled, open proposals cancelled |

`PlanIn = {activity_type, title, goal_text, city, public_location?, timezone, start_date, end_date, intent, interests[], group_min(2-4), group_max(2-4), group_only, preview_text?, windows: [{starts_at, ends_at}]}`
Validation: end_date ≥ start_date, ends_at > starts_at, 2 ≤ group_min ≤ group_max ≤ 4.

`PlanOut = PlanIn + {id, discovery_mode, status, cover_image_url, ai_consent: bool, created_at, latest_proposal_id|null, latest_run_id|null}`

## Agent — `app/api/agent.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/agent/runs | `{plan_id, goal?}` | `RunOut` (202). Requires plan.ai_consent (else 409 `{"detail":"ai_consent_required"}`) and `can_discover` (else 403 `{"detail":"not_eligible"}`). Runs in background. |
| GET | /api/agent/runs/{id} | – | `RunOut` (owner only) — frontend polls every 1s while `status=running` |

`RunOut = {id, plan_id, proposal_id|null, trigger, mode: "ml" (older runs: "live"|"offline"), status, summary|null, error|null, model|null, created_at, finished_at|null, events: [{seq, kind:"tool"|"review"|"system"|"error" (older runs also "model"), agent|null, tool_name|null, summary, created_at}]}`

`mode=ml` means the run used the InGather matcher (`model` = its version, e.g. `matcher-1`), a machine-learning model served on the backend; no LLM is called and MODEL_API_KEY is not needed. See *Gather engine* below.

## Proposals / invitations — `app/api/proposals.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/proposals/{id} | – | `ProposalOut`, shaped by viewer stage (below) |
| POST | /api/proposals/{id}/members/{user_id}/pass | `{feedback?: "prefer_same_event"|"prefer_group"|"different_activity"|"schedule"|null}` | `RunOut` — owner only; marks passed (candidate never notified) and starts a replan run |
| POST | /api/proposals/{id}/replan | `{feedback?}` | `RunOut` — owner asks for different people |
| POST | /api/proposals/{id}/approve-invitations | `{version, user_ids[]}` | `ProposalOut` — owner only; user_ids ⊆ current `suggested` members and version must match, else 409 |
| GET | /api/invitations | – | `[InvitationOut]` invitations addressed to me |
| POST | /api/proposals/{id}/respond | `{accept: bool}` | `ProposalOut` — invited member only; decline enqueues outbox `invitation_declined` → replan run |
| POST | /api/proposals/{id}/finalize | `{start_at?, end_at?, venue_label?, venue_category?, venue_place_id?}` | `ProposalOut` — owner; requires ≥1 accepted and no invites pending; bumps version, status→awaiting_final, clears confirmations |
| POST | /api/proposals/{id}/confirm | `{version}` | `ProposalOut` — owner or accepted member; when all confirmed for current version → `confirmed` (+ agent icebreaker message) |
| POST | /api/proposals/{id}/leave | – | `ProposalOut`/204 — member leaves; owner leaving = cancel |
| GET | /api/proposals/{id}/messages | – | `[MessageOut]` — confirmed proposals, current participants only |
| POST | /api/proposals/{id}/messages | `{body (1-1000)}` | `MessageOut` |
| GET | /api/proposals/{id}/venue-poll | – | `VenuePollOut` — owner or accepted member (else 404); `status:"not_started"` until someone starts it |
| POST | /api/proposals/{id}/venue-poll | – | `VenuePollOut` — any participant; status `invites_pending` (nobody still invited, ≥1 accepted) or `awaiting_final`; runs the venue agent (sync, ≤~60 s live); idempotent once started. 409 `invites_pending`/`no_accepted_members`/`not_open`/`invalid_time` |
| GET | /api/groups | – | `[GroupOut]`: every group I host or have joined (accepted), with status invites_pending, awaiting_final or confirmed, soonest first. Groups with someone I blocked (or who blocked me) are left out. `GroupOut = {proposal_id, activity_title, activity_type, city, date, status, role: "host"\|"member", host_name, members: [{first_name, avatar_url}]}`, host first. Shown as "Your groups" on Home |
| POST | /api/proposals/{id}/venue-poll/rate | `{option_id, score: 1-10}` | `VenuePollOut`: each participant rates each option 1-10, and re-posting changes the score. When every current participant has rated every option, the winner is the highest average (a tie goes to the agent's better rank). The winner becomes `venue_*` (with coordinates in `venue_details`), the **version bumps, confirmations reset, and status becomes awaiting_final**. 409 `venue_poll_closed`/`option_not_found`/`no_venue_poll` |
| PUT | /api/proposals/{id}/location | `{latitude, longitude}` | `VenuePollOut`: opt-in, per proposal. Stored rounded to about 100 m and shown only to this proposal's owner and accepted members, on the meetup map and for travel times. When anyone shares, the venue search centres on the midpoint of shared locations instead of home areas |
| DELETE | /api/proposals/{id}/location | – | `VenuePollOut`: stop sharing (the stored point is deleted) |
| POST | /api/proposals/{id}/venue-poll/reroll | – | `VenuePollOut`: "find more places". It returns 3 new options for a new round (ratings apply per round), up to 3 times per proposal (409 `reroll_used`) |
| GET | /api/proposals/{id}/calendar.ics | – | `text/calendar` VEVENT (UID, DTSTART/DTEND UTC, SUMMARY, LOCATION venue, DESCRIPTION with Gather Room link). Confirmed proposals, participants only; else 404 |

`VenuePollOut = {status: "not_started"|"open"|"decided", round, rerolls_left, source: "google"|"grounded"|"fallback"|null, options: [{id, rank, name, area|null, category, why, description, latitude|null, longitude|null, image_url|null, place: PlaceOut|null, reservation_url|null, source_url|null, verified, average|null, ratings, my_score|null}], voters: [{user_id, display_name, voted, rated}], people: [{user_id, display_name, avatar_url|null, latitude, longitude, is_me}], i_shared_location, winner_option_id|null, proposal_version}`. `voters` shows *how many* options each person has rated (`voted` means all of them), never their scores. `people` lists only those who chose to share their location. Coordinates and `image_url` are kept only for verified options; pins more than 30 km from the group midpoint are dropped, and a verified option without coordinates is geocoded with Nominatim. `verified=true` only when the venue's source URL was returned by the Muse Spark web_search grounding; otherwise it is labeled "Suggestion — not verified". Offline/failure options are generic public-place kinds, never invented names. The model sees only the city, the rounded group midpoint (from shared locations, otherwise participants' ~1 km home-area points), local meetup time, activity title and shared interests.

**Google Maps (optional, `GOOGLE_MAPS_API_KEY`).** With a key, the venue agent first asks Google Places (New) Text Search for real places near the group, using the activity title plus city as the query and the rounded midpoint as a location bias. Places farther than 30 km, closed places and private kinds (lodging and the like) are dropped. Muse Spark then picks 3 from those candidates without web search, which takes a few seconds; if Muse is unavailable, a heuristic picks them (rating, review count, distance). These options have `source:"google"`, exact pins and `place`. Without a key, web-search picks are pinned with OpenStreetMap: full address, then street address, then name + city, rejecting pins more than 50 km from the group. When a key is set, web-search picks are first looked up on Google, three in parallel.

`PlaceOut = {type|null, rating|null, rating_count|null, price: "$".."$$$$"|"Free"|null, open_now|null, hours: [string] (Google weekday lines), phone|null, website|null, maps_url|null, summary|null, photos: [{url, author|null}]}`

| GET | /api/venue-photos/{option_id}/{index} | – | 302 to a short-lived Google photo URL (no API key in it); 404 if that option has no such photo. No login, because `<img>` can't send a token. Only photos stored on a venue option can be fetched, by its unguessable id. |

`ProposalOut = {id, plan_id, version, status, activity_title, explanation, start_at, end_at, timezone, city, venue_label, venue_category, venue_verified, icebreaker, viewer_role: "owner"|"invitee"|"member", members: [MemberOut], group_size, my_status, i_confirmed: bool}`

`MemberOut = {user_id, display_name, avatar_url, interests[], is_initiator, status, reason|null, confirmed: bool, details: string[]}`

`details` are human-readable "about you" chips (e.g. `["Woman", "25–34", "Software engineer at Dell", "UT Austin, CS"]`) holding only the fields that person switched on (gender / age range / education+work). Only owner and member viewers ever receive a roster, so invitees, strangers and the feed never see them. The same `details` appear on `ChatPerson` in `GET /api/chats` (everyone there comes from a confirmed meetup). These fields are never used for matching or ranking and never sent to an AI model.

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

# app/services/gather.py
class GatherEngine:
    def __init__(self, db, settings, matching=None): ...    # matching (and its model) injectable for tests
    def run(self, run_id: UUID) -> None                     # executes AgentRun, writes events, saves proposal
def start_run(db, owner: User, plan: Plan, trigger: str, goal: str = "", excluded: set[UUID] = ()) -> AgentRun
def run_in_background(run_id: UUID) -> None                 # opens its own Session; used by BackgroundTasks / outbox
```

---

# v2 additions (AI plan intake, verification; the v2 agent orchestra was replaced by the v3 gather engine)

## Verification — `app/api/verification.py` + `app/services/identity.py`
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/verification | – | `VerificationOut` |
| POST | /api/verification/demo | `{confirm_adult: true}` | `MeOut`. **DEMO_MODE only** (else 404). Sets `verification=verified_demo`, `is_adult=true`, `verification_provider="demo"`, writes ConsentEvent `verification_demo`. 422 if `confirm_adult` is not true. Never upgrades `verified_live` down. |
| POST | /api/verification/stripe/start | – | `{url}` — creates a Stripe Identity VerificationSession (type `document`, `metadata.user_id`, `return_url=PUBLIC_BASE_URL/verify?done=1`), stores `verification_session_id`, provider `stripe`. 503 `{"detail":"stripe_unavailable"}` without `STRIPE_SECRET_KEY`. |
| POST | /api/webhooks/stripe | raw Stripe event | 200. **Signature-verified** with `STRIPE_WEBHOOK_SECRET` (HMAC-SHA256 `Stripe-Signature`, 5-min tolerance) else 400. On `identity.verification_session.verified`: look up user by stored session id (never by metadata alone), retrieve the session with `expand[]=verified_outputs` to read `dob`, set `verification=verified_live`, `is_adult` from DOB ≥ 18, `verified_at`. Idempotent. Other events: 200 no-op. |

`VerificationOut = {status: "unverified"|"verified_demo"|"verified_live", provider: "demo"|"stripe"|null, is_adult, verified_at|null, demo_available: bool (DEMO_MODE), stripe_available: bool (key set), stripe_test_mode: bool (key starts sk_test_)}`

UI copy rules: `verified_demo` → "Demo account · verification simulated — no ID checked". `verified_live` in Stripe **test mode** → "Stripe Identity test mode — not a real ID check". Never say "safe".

## AI plan intake — `POST /api/plans/draft` (in `app/ai/routes.py`)
Body `{text (1-2000), timezone_hint?: IANA}` → `PlanDraftOut` (nothing is saved):
`{activity_type|null, title|null, goal_text, city|null, timezone|null, start_date|null, end_date|null, intent|null, interests: [], group_min|null, group_max|null, group_only|null, windows: [{starts_at, ends_at}] (UTC ISO), missing: [field names it could not infer], notes: str (one sentence, e.g. "Assumed 2026 because the dates are upcoming"), mode: "live"}`
Uses the **Intake agent** (Muse Spark, structured output, no tools), told today's date (server, in timezone_hint) so relative/past dates resolve to the next future occurrence. Validates output through the same rules as `PlanIn` (2≤min≤max≤4, end≥start, known activity types) and drops invalid fields into `missing`. 503 `ai_unavailable` without key. Rate-limited.

## Gather engine — `app/services/gather.py` + `app/ml/` (v3: replaces the agent orchestra behind the SAME `start_run` / `run_in_background` / `RunOut` API)
No LLM. One pass of plain server code around an ML model:
1. **matcher** — `Matching.fits()` applies the hard filters (opted in, verified, adult, same city and dates, overlapping free time, not blocked, not excluded, not already on a proposal), then scores each person with the **InGather matcher**: gradient-boosted trees over 11 pair features (exact and embedding-based interest similarity, same activity / intent / event, hours of shared free time). Trained by `backend/ml/train.py` on the public Meetup.com dataset plus simulated plan context; see `backend/ml/README.md`. Interests named in the owner's run note (`goal`) are added for that run.
2. **scheduler** — searches every group of the allowed size among the 10 best-scoring people for one that shares a window of ≥ 60 minutes with the owner (and anyone still on the proposal). Utility = 0.7 × mean owner fit + 0.3 × mean pairwise fit between the people (same model) + small bonuses for size and longer windows. The slot is 90 minutes from the window start, rounded up to the half hour.
3. **venue** — nearest mapped public place of a kind that suits the activity (cafe for coffee/conference, library for study, …), else a generic public suggestion.
4. **checks** — group size, nobody excluded or blocked, public venue category and label, slot inside the shared window. Any failure ends the run (`checks_failed`); `Proposals.save_agent_result` then re-validates everything again.
Replans (`pass`, `decline`, `feedback`) keep people still on the open proposal and fill open slots. Feedback adjusts the search: `prefer_group` (largest feasible group first), `prefer_same_event` (same event location first), `schedule` (a different window than last time), `different_activity` (a different venue kind).

`RunOut.events[]`: `agent` is the step (`"gather"|"matcher"|"scheduler"|"venue"|"checks"`; older runs may carry the former agent names), `kind` is `"tool"` for real backend steps (`find_eligible_candidates`, `score_candidates`, `check_group_availability`, `find_nearby_places`, `propose_group`), `"review"` for passed checks (`safety_checks`), `"system"` for notes and `"error"` for failures. Run errors: `plan_inactive`, `no_suitable_group`, `checks_failed`, `propose_failed`, `internal_error`.

### Public-event venue lookup

`public_location` is an optional owner-private public event venue/address (max 200 characters). Lookup sends only that value and city to Nominatim, then public coordinates to Overpass. `places` contains `{id, name, category, latitude, longitude, address, distance_m, source}` within 1.5 km, sorted by straight-line distance. A provider failure returns `status=unavailable` and an empty list. Successful lookups are cached for 30 minutes.

`venue_place_id` must match a server-returned place for this plan. Selection stores `ProposalOut.venue_details` with the chosen meetup coordinates, never the event origin. It follows venue disclosure: owner, then accepted members during final confirmation/confirmed states. Manual venue changes clear the old coordinates. A map listing does not set `venue_verified` or imply a booking.

### Messaging inbox and individual conversations

`GET /api/chats` returns the signed-in user's confirmed group chats and individual connections as `{id, kind: "group"|"direct", title, people: [{user_id, display_name, avatar_url}], last_message, last_sender_name, updated_at}`. Only the user's own message previews are included. No contact details are returned.

`GET /api/chats/people/{user_id}/messages` returns the latest 200 direct messages in chronological order (`MessageOut`). `POST` to the same path accepts `MessageIn` and returns the stored `MessageOut` (201); sender identity always comes from authentication. Both endpoints require a connection established by a fully confirmed shared meetup. Connections persist after the meetup. Self, unconnected and blocked peers return 404 in either direction; sending uses the existing per-user message rate limit. Group chat remains on `/api/proposals/{id}/messages` and is kept separate from direct messages.


## Home feed and join requests — `app/api/feed.py`, `app/services/feed.py` (v4)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/feed?sort=match\|soonest&activity=<ActivityType> | – | `[FeedItemOut]`: up to 50 open groups for the viewer, optionally only one kind of plan (the Home category tabs) (empty unless `can_discover`). `match` (default) orders by the displayed fit, sooner first on ties; `soonest` orders by start time, best fit first on ties. Groups the viewer joined or asked to join always come first. The UI also filters by day (Any day / Today / Tomorrow / This weekend). |
| POST | /api/proposals/{id}/join | `{message?: str ≤400}` | `FeedItemOut` (201). 404 unless the group is joinable and visible to the viewer. Idempotent while pending or accepted; a declined requester gets 404. In DEMO_MODE a fictional host answers a few seconds later. |
| DELETE | /api/proposals/{id}/join | – | 204: withdraws a pending request. |
| POST | /api/proposals/{id}/join/draft | – | `{message, mode: "live"\|"template"}`: Muse Spark drafts an intro from the viewer's own bio and interests. Nothing is sent. |
| GET | /api/proposals/{id}/join-requests | – | `[JoinRequestOut]`: owner only, pending requests. |
| POST | /api/proposals/{id}/join-requests/{rid}/accept\|decline | – | `[JoinRequestOut]`: owner only. Accepting adds an `accepted` member, bumps the version (earlier confirmations no longer count) and stores a Muse-written welcome note. 409 `group_full_or_closed` if there's no room. |
| POST | /api/proposals/{id}/open | `{open: bool}` | 204: owner turns "Let people ask to join" on or off. |
| GET | /api/demo/avatars/{atx-NNNN}.svg | – | Illustrated portrait for a fictional Austin resident. |

A group is joinable while `open_to_requests`, status is `invites_pending` or `awaiting_final`, it hasn't started, its plan is active and in `mutual_discovery`, and it has open spots (group_max, max 4, minus host and invited or accepted members). Blocks in either direction with the host or any member hide it.

`FeedItemOut = {proposal_id, title, activity_type, city, day (local date), part_of_day: morning|afternoon|evening, venue_kind, preview, host: {first_name, avatar_url}, members: [...], group_size, spots_left, group_interests, shared_interests, match: 0-100, reason, free_then: bool|null, request_status: pending|accepted|declined|withdrawn|null, welcome|null}`. There's no exact time, venue name or full names until accepted.

The match score is the matcher's fit probability, assuming the timing and activity work. The feed's ranking uses the viewer's real context: same activity and intent as their plan in that city, and hours free during the slot.

`JoinRequestOut = {id, user_id, display_name, avatar_url, bio, interests, message, match, status, created_at}`.
