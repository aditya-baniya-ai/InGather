// Typed client for docs/api-contract.md. Same-origin relative URLs (Vite proxies in dev,
// FastAPI serves the build in prod).

export type Verification = "unverified" | "verified_demo" | "verified_live";
export type DiscoveryMode = "private_browse" | "mutual_discovery" | "paused";
export type PlanStatus = "active" | "paused" | "cancelled" | "expired";
export type ProposalStatus = "pending_owner" | "invites_pending" | "awaiting_final" | "confirmed" | "cancelled";
export type MemberStatus = "suggested" | "passed" | "invited" | "accepted" | "declined" | "expired" | "removed";
export type ViewerRole = "owner" | "invitee" | "member";
export type Feedback = "prefer_same_event" | "prefer_group" | "different_activity" | "schedule";
export type EventKind = "tool" | "model" | "system" | "error" | "review";
/** Steps of the gather pipeline (app/services/gather.py). Older runs may carry other names. */
export type AgentName = "gather" | "matcher" | "scheduler" | "venue" | "checks";

export interface Me {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  interests: string[];
  verification: Verification;
  is_demo: boolean;
  discovery_paused: boolean;
  group_only: boolean;
  can_discover: boolean;
  /** Private coarse home area (city / neighborhood / ZIP). Only ever returned to its owner. */
  home_area?: string | null;
  home_area_located?: boolean;
}
export interface ChatPerson { user_id: string; display_name: string; avatar_url: string | null }
export interface Conversation { id: string; kind: "group" | "direct"; title: string; people: ChatPerson[]; last_message: string | null; last_sender_name: string | null; updated_at: string }
export interface TokenOut { access_token: string; token_type: "bearer"; user: Me }
export interface DemoAccount { email: string; display_name: string; avatar_url: string | null; bio: string | null }

export interface Window { starts_at: string; ends_at: string }
export interface PlanIn {
  activity_type: string;
  title: string;
  goal_text: string;
  city: string;
  public_location?: string | null;
  timezone: string;
  start_date: string;
  end_date: string;
  intent: string;
  interests: string[];
  group_min: number;
  group_max: number;
  group_only: boolean;
  preview_text?: string | null;
  windows: Window[];
}
export interface Plan extends PlanIn {
  id: string;
  discovery_mode: DiscoveryMode;
  status: PlanStatus;
  cover_image_url: string | null;
  ai_consent: boolean;
  created_at: string;
  latest_proposal_id: string | null;
  latest_run_id: string | null;
}

export interface RunEvent { seq: number; kind: EventKind; agent?: string | null; tool_name: string | null; summary: string; created_at: string }
export interface Run {
  id: string;
  plan_id: string;
  proposal_id: string | null;
  trigger: string;
  /** "ml" = the InGather matcher; "live"/"offline" only on runs from before the matcher. */
  mode: "ml" | "live" | "offline";
  status: "running" | "completed" | "failed";
  summary: string | null;
  error: string | null;
  model: string | null;
  created_at: string;
  finished_at: string | null;
  events: RunEvent[];
}

export interface Member {
  user_id: string;
  display_name: string;
  avatar_url: string | null;
  interests: string[];
  is_initiator: boolean;
  status: MemberStatus;
  reason: string | null;
  confirmed: boolean;
}
export interface Proposal {
  id: string;
  plan_id: string;
  version: number;
  status: ProposalStatus;
  activity_title: string;
  initiator_name: string;
  initiator_user_id: string;
  /** Owner only: newest agent run for this plan. */
  latest_run_id: string | null;
  /** "" for everyone but the owner. */
  explanation: string;
  /** UTC ISO once final details exist; a plain local date ("2027-01-17") for invitees and pre-final members. */
  start_at: string | null;
  end_at: string | null;
  timezone: string;
  city: string;
  venue_label: string | null;
  venue_category: string | null;
  venue_verified: boolean;
  venue_details?: VenuePlace | null;
  icebreaker: string | null;
  viewer_role: ViewerRole;
  members: Member[];
  group_size: number;
  my_status: MemberStatus | null;
  i_confirmed: boolean;
  /** Owner only: people can ask to join from their Home feed. */
  open_to_requests?: boolean;
}
export interface Invitation {
  proposal_id: string;
  activity_title: string;
  city: string;
  date: string | null;
  group_size: number;
  from_user_id: string;
  from_display_name: string;
  from_avatar_url: string | null;
  status: MemberStatus;
  expires_at: string | null;
}
export interface VerificationOut {
  status: Verification;
  provider: "demo" | "stripe" | null;
  is_adult: boolean;
  verified_at: string | null;
  demo_available: boolean;
  stripe_available: boolean;
  stripe_test_mode: boolean;
}

/** AI intake draft: nothing is saved. Windows are UTC ISO. */
export interface PlanDraft {
  activity_type: string | null;
  title: string | null;
  goal_text: string;
  city: string | null;
  public_location?: string | null;
  timezone: string | null;
  start_date: string | null;
  end_date: string | null;
  intent: string | null;
  interests: string[];
  group_min: number | null;
  group_max: number | null;
  group_only: boolean | null;
  windows: Window[];
  missing: string[];
  notes: string;
  mode: "live";
}

export interface Message { id: string; sender_id: string | null; sender_name: string; body: string; created_at: string }
export interface BlockedUser { user_id: string; display_name: string }
export interface FeedPerson { first_name: string; avatar_url: string | null }
/** An open group as a non-member sees it: day and part of day, kind of place, first names. */
export interface FeedItem {
  proposal_id: string; title: string; activity_type: string; city: string; day: string; part_of_day: "morning" | "afternoon" | "evening";
  venue_kind: string; preview: string | null; host: FeedPerson; members: FeedPerson[]; group_size: number; spots_left: number;
  group_interests: string[]; shared_interests: string[]; match: number; reason: string; free_then: boolean | null;
  request_status: "pending" | "accepted" | "declined" | "withdrawn" | null; welcome: string | null;
}
export interface JoinRequest { id: string; user_id: string; display_name: string; avatar_url: string | null; bio: string | null; interests: string[]; message: string | null; match: number | null; status: string; created_at: string }

export interface VenuePlace { id: string; name: string; category: string; latitude: number; longitude: number; address: string; distance_m: number; source: string; reservation_url?: string | null; source_url?: string | null }
export interface NearbyPlaces { status: string; message: string; places: VenuePlace[]; origin?: { latitude: number; longitude: number; label: string } }
export interface FinalizeIn { venue_place_id?: string; start_at?: string; end_at?: string; venue_label?: string; venue_category?: string }
export type MePatch = Partial<Pick<Me, "display_name" | "bio" | "interests" | "avatar_url" | "discovery_paused" | "group_only" | "home_area">>;

export interface VenueOption {
  id: string; rank: number; name: string; area: string | null; category: string; why: string; description: string;
  latitude: number | null; longitude: number | null; image_url: string | null;
  reservation_url: string | null; source_url: string | null; verified: boolean;
  average: number | null; ratings: number; my_score: number | null;
}
export interface Voter { user_id: string; display_name: string; voted: boolean; rated: number }
/** A group member who shared their location with this group (rounded to ~100 m). */
export interface MapPerson { user_id: string; display_name: string; avatar_url: string | null; latitude: number; longitude: number; is_me: boolean }
export interface VenuePoll {
  status: "not_started" | "open" | "decided"; round: number; rerolls_left: number; source: "grounded" | "fallback" | null;
  options: VenueOption[]; voters: Voter[]; people: MapPerson[]; i_shared_location: boolean;
  winner_option_id: string | null; proposal_version: number;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

const TOKEN_KEY = "ingather.token";
export const tokenStore = {
  get(): string | null {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch { /* storage unavailable: session lives in memory only */ }
  },
};

type Body = object | FormData | undefined;

export class ApiClient {
  private memToken: string | null = tokenStore.get();
  onUnauthorized: () => void = () => {};

  get token() { return this.memToken; }
  setToken(token: string | null) {
    this.memToken = token;
    tokenStore.set(token);
  }

  async request<T>(method: string, path: string, body?: Body): Promise<T> {
    const headers: Record<string, string> = {};
    if (this.memToken) headers.Authorization = `Bearer ${this.memToken}`;
    let payload: BodyInit | undefined;
    if (body instanceof FormData) payload = body;
    else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    const res = await fetch(path, { method, headers, body: payload });
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      this.setToken(null);
      this.onUnauthorized();
    }
    if (!res.ok) {
      let detail = res.statusText || "Request failed";
      try {
        const data = await res.json();
        if (typeof data?.detail === "string") detail = data.detail;
        else if (Array.isArray(data?.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
      } catch { /* non-JSON error */ }
      throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  private get = <T,>(p: string) => this.request<T>("GET", p);
  private post = <T,>(p: string, b: Body = {}) => this.request<T>("POST", p, b);

  // auth
  login = (email: string, password: string) => this.post<TokenOut>("/api/auth/login", { email, password });
  register = (email: string, password: string, display_name: string) =>
    this.post<TokenOut>("/api/auth/register", { email, password, display_name });
  demoAccounts = () => this.get<DemoAccount[]>("/api/auth/demo-accounts");
  demoLogin = (email: string) => this.post<TokenOut>("/api/auth/demo-login", { email });
  authConfig = () => this.get<{ supabase_url: string | null; supabase_anon_key: string | null; demo_mode: boolean }>("/api/auth/config");
  supabaseSession = (access_token: string, display_name?: string) =>
    this.post<TokenOut>("/api/auth/supabase", display_name ? { access_token, display_name } : { access_token });
  me = () => this.get<Me>("/api/me");
  updateMe = (patch: MePatch) => this.request<Me>("PATCH", "/api/me", patch);

  // verification
  verification = () => this.get<VerificationOut>("/api/verification");
  demoVerify = () => this.post<Me>("/api/verification/demo", { confirm_adult: true });
  stripeStart = () => this.post<{ url: string }>("/api/verification/stripe/start");

  // plans
  draftPlan = (text: string, timezone_hint: string) => this.post<PlanDraft>("/api/plans/draft", { text, timezone_hint });
  plans = () => this.get<Plan[]>("/api/plans");
  plan = (id: string) => this.get<Plan>(`/api/plans/${id}`);
  createPlan = (plan: PlanIn) => this.post<Plan>("/api/plans", plan);
  nearbyPlaces = (id: string) => this.get<NearbyPlaces>(`/api/plans/${id}/nearby`);
  updatePlan = (id: string, patch: Partial<PlanIn>) => this.request<Plan>("PATCH", `/api/plans/${id}`, patch);
  setDiscovery = (id: string, mode: DiscoveryMode, ai_consent?: boolean) =>
    this.post<Plan>(`/api/plans/${id}/discovery`, ai_consent === undefined ? { mode } : { mode, ai_consent });
  deletePlan = (id: string) => this.request<void>("DELETE", `/api/plans/${id}`);
  generateCover = (id: string) => this.post<Plan>(`/api/plans/${id}/cover`);

  // agent
  startRun = (plan_id: string, goal?: string) => this.post<Run>("/api/agent/runs", goal ? { plan_id, goal } : { plan_id });
  run = (id: string) => this.get<Run>(`/api/agent/runs/${id}`);

  // proposals
  proposal = (id: string) => this.get<Proposal>(`/api/proposals/${id}`);
  pass = (id: string, userId: string, feedback: Feedback | null) =>
    this.post<Run>(`/api/proposals/${id}/members/${userId}/pass`, { feedback });
  replan = (id: string, feedback: Feedback | null) => this.post<Run>(`/api/proposals/${id}/replan`, { feedback });
  approveInvitations = (id: string, version: number, user_ids: string[]) =>
    this.post<Proposal>(`/api/proposals/${id}/approve-invitations`, { version, user_ids });
  invitations = () => this.get<Invitation[]>("/api/invitations");
  respond = (id: string, accept: boolean) => this.post<Proposal>(`/api/proposals/${id}/respond`, { accept });
  venuePoll = (id: string) => this.get<VenuePoll>(`/api/proposals/${id}/venue-poll`);
  startVenuePoll = (id: string) => this.post<VenuePoll>(`/api/proposals/${id}/venue-poll`);
  rateVenue = (id: string, option_id: string, score: number) => this.post<VenuePoll>(`/api/proposals/${id}/venue-poll/rate`, { option_id, score });
  shareLocation = (id: string, latitude: number, longitude: number) => this.request<VenuePoll>("PUT", `/api/proposals/${id}/location`, { latitude, longitude });
  stopSharingLocation = (id: string) => this.request<VenuePoll>("DELETE", `/api/proposals/${id}/location`);
  rerollVenues = (id: string) => this.post<VenuePoll>(`/api/proposals/${id}/venue-poll/reroll`);
  /** Downloads the .ics with the bearer token (a plain link can't carry it). */
  downloadCalendar = async (id: string) => {
    const res = await fetch(`/api/proposals/${id}/calendar.ics`, { headers: this.memToken ? { Authorization: `Bearer ${this.memToken}` } : {} });
    if (!res.ok) throw new ApiError(res.status, res.statusText || "Request failed");
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "ingather-meetup.ics" });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  finalize = (id: string, body: FinalizeIn) => this.post<Proposal>(`/api/proposals/${id}/finalize`, body);
  confirm = (id: string, version: number) => this.post<Proposal>(`/api/proposals/${id}/confirm`, { version });
  leave = (id: string) => this.post<Proposal | undefined>(`/api/proposals/${id}/leave`);
  messages = (id: string) => this.get<Message[]>(`/api/proposals/${id}/messages`);
  sendMessage = (id: string, body: string) => this.post<Message>(`/api/proposals/${id}/messages`, { body });

  // home feed & join requests
  feed = (sort: "match" | "soonest" = "match", activity?: string | null) =>
    this.get<FeedItem[]>(`/api/feed?sort=${sort}${activity ? `&activity=${encodeURIComponent(activity)}` : ""}`);
  askToJoin = (id: string, message: string | null) => this.post<FeedItem>(`/api/proposals/${id}/join`, { message });
  withdrawJoin = (id: string) => this.request<void>("DELETE", `/api/proposals/${id}/join`);
  draftJoin = (id: string) => this.post<{ message: string; mode: "live" | "template" }>(`/api/proposals/${id}/join/draft`);
  joinRequests = (id: string) => this.get<JoinRequest[]>(`/api/proposals/${id}/join-requests`);
  decideJoin = (id: string, requestId: string, accept: boolean) =>
    this.post<JoinRequest[]>(`/api/proposals/${id}/join-requests/${requestId}/${accept ? "accept" : "decline"}`);
  setOpen = (id: string, open: boolean) => this.post<void>(`/api/proposals/${id}/open`, { open });

  chats = () => this.get<Conversation[]>("/api/chats");
  deleteChat = (id: string) => this.request<void>("DELETE", `/api/chats/people/${id}`);
  directMessages = (id: string) => this.get<Message[]>(`/api/chats/people/${id}/messages`);
  sendDirectMessage = (id: string, body: string) => this.post<Message>(`/api/chats/people/${id}/messages`, { body });

  // safety
  block = (user_id: string) => this.post<void>("/api/blocks", { user_id });
  blocks = () => this.get<BlockedUser[]>("/api/blocks");
  unblock = (user_id: string) => this.request<void>("DELETE", `/api/blocks/${user_id}`);
  report = (body: { reason: string; details?: string; reported_user_id?: string; proposal_id?: string }) =>
    this.post<void>("/api/reports", body);

  // AI extras
  transcribe = (wav: Blob) => {
    const form = new FormData();
    form.append("audio", wav, "voice.wav");
    return this.post<{ text: string }>("/api/voice/transcribe", form);
  };
  createConnectorToken = () => this.post<{ token: string }>("/api/connector/tokens");
  revokeConnectorTokens = () => this.request<void>("DELETE", "/api/connector/tokens");
}

export const api = new ApiClient();

const DETAIL_COPY: Record<string, string> = {
  ai_consent_required: "Turn on AI processing for this plan first.",
  not_eligible: "Your account can't use discovery yet: verify your account, or turn off \"Pause all discovery\" in Profile.",
  plan_inactive: "This plan is paused or cancelled. Resume it to continue.",
  stale_version: "The proposal changed while you were looking. Review the latest version and try again.",
  not_suggested: "That person is no longer a current suggestion. Review the latest list.",
  candidate_unavailable: "That person is no longer available for this plan.",
  no_common_time: "That group doesn't share a free time. Try different people or times.",
  not_awaiting_approval: "There's nothing waiting for your approval right now.",
  invites_pending: "Wait until everyone invited has answered.",
  no_accepted_members: "At least one person needs to accept before you set final details.",
  invalid_time: "Check the time: it must end after it starts and fit the plan's dates.",
  not_awaiting_final: "These details aren't waiting for confirmation anymore.",
  already_accepted: "You've already accepted this invitation.",
  invitation_expired: "This invitation has expired.",
  not_open: "This meetup is no longer open.",
  email_taken: "An account with that email already exists. Try signing in.",
  use_supabase: "Sign-up now goes through the email sign-in above. Reload the page and try again.",
  transcription_failed: "Couldn't transcribe that. You can type instead.",
  ai_unavailable: "This AI feature is unavailable right now.",
  draft_failed: "The Intake agent couldn't draft that. Try rephrasing it, or fill the form manually.",
  stripe_unavailable: "Stripe Identity isn't set up on this server.",
  no_suitable_group: "No compatible group is free right now. Try again later or widen your times.",
  checks_failed: "The safety checks didn't pass, so nothing was proposed.",
  propose_failed: "The group changed while it was being saved. Try again.",
  internal_error: "Something went wrong while finding a group.",
  reroll_used: "You've already asked for new options once. Pick one of these, or the organizer can set a place.",
  venue_poll_closed: "Voting has finished. Confirm the winning place below.",
  option_not_found: "Those options changed. Pick again from the new ones.",
  no_venue_poll: "Nobody has started the venue vote yet.",
};

/** Friendly copy for a backend detail code (or the code itself). */
export const detailCopy = (detail: string) => DETAIL_COPY[detail] ?? detail;

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (DETAIL_COPY[err.detail]) return DETAIL_COPY[err.detail];
    if (err.status === 401) return "Wrong email or password.";
    if (err.status === 404) return "Not found, or you don't have access.";
    if (err.status === 429) return "Too many requests. Wait a moment and try again.";
    if (err.status === 503) return "This AI feature is unavailable right now.";
    return err.detail;
  }
  if (err instanceof TypeError) return "Can't reach InGather. Check your connection and try again.";
  if (err instanceof Error && err.name === "SupabaseAuthError") return err.message;
  return "Something went wrong.";
}
