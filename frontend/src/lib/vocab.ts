import type { DiscoveryMode, Feedback, MemberStatus, ProposalStatus, Verification } from "./api";

export const ACTIVITIES = [
  { value: "conference", label: "Conference" },
  { value: "travel", label: "Travel" },
  { value: "hackathon", label: "Hackathon" },
  { value: "study", label: "Study" },
  { value: "coffee", label: "Coffee & food" },
  { value: "event", label: "Local event" },
  { value: "other", label: "Other" },
];
export const activityLabel = (v: string) => ACTIVITIES.find((a) => a.value === v)?.label ?? v;

/** Story-style categories on Home. `null` = show everything. */
export const CATEGORIES: { label: string; activity: string | null }[] = [
  { label: "Explore", activity: null },
  { label: "Travel", activity: "travel" },
  { label: "Conference", activity: "conference" },
  { label: "Study", activity: "study" },
  { label: "Coffee", activity: "coffee" },
  { label: "Hackathon", activity: "hackathon" },
  { label: "Events", activity: "event" },
];

export const INTENTS = [
  { value: "friends", label: "Friends" },
  { value: "networking", label: "Networking" },
  { value: "activity", label: "Activity partner" },
];

export const INTEREST_SUGGESTIONS = ["technology", "food", "museums", "walking", "photography", "coffee", "music", "design", "startups", "history", "art", "running"];

export const FEEDBACK: { value: Feedback | null; label: string }[] = [
  { value: "prefer_same_event", label: "Prefer same event" },
  { value: "prefer_group", label: "Prefer group" },
  { value: "different_activity", label: "Different activity" },
  { value: "schedule", label: "Schedule doesn't fit" },
  { value: null, label: "No reason" },
];

export const VENUE_CATEGORIES = [
  { value: "cafe", label: "Café" },
  { value: "restaurant", label: "Restaurant" },
  { value: "museum", label: "Museum" },
  { value: "park", label: "Park" },
  { value: "food_hall", label: "Food hall" },
  { value: "library", label: "Library" },
  { value: "conference_venue", label: "Event venue" },
  { value: "public_venue", label: "Other public place" },
];

export const DISCOVERY: Record<DiscoveryMode, { label: string; help: string }> = {
  private_browse: { label: "Private · AI suggests people", help: "Nobody can see this plan. Our matcher suggests people you could reach out to, and nobody is contacted until you approve." },
  mutual_discovery: { label: "Public · post it for everyone", help: "Your plan appears on Home for people with similar interests. They ask to join and you decide. Exact times and places stay hidden until you accept someone." },
  paused: { label: "Paused", help: "No searching and no new suggestions until you resume." },
};

export const MEMBER_STATUS: Record<MemberStatus, { label: string; tone: "neutral" | "rose" | "violet" | "emerald" | "amber" | "danger" }> = {
  suggested: { label: "Suggested", tone: "violet" },
  passed: { label: "Passed · not notified", tone: "neutral" },
  invited: { label: "Invitation pending", tone: "amber" },
  accepted: { label: "Accepted", tone: "emerald" },
  declined: { label: "Couldn't join", tone: "neutral" },
  expired: { label: "Expired", tone: "neutral" },
  removed: { label: "Removed", tone: "neutral" },
};

export const PROPOSAL_STATUS: Record<ProposalStatus, string> = {
  pending_owner: "Waiting for your approval",
  invites_pending: "Invitations out",
  awaiting_final: "Confirming final details",
  confirmed: "Confirmed",
  cancelled: "Cancelled",
};

export const VERIFICATION: Record<Verification, { label: string; detail: string }> = {
  unverified: { label: "Not verified", detail: "Discovery stays off until identity and adulthood are verified." },
  verified_demo: { label: "Demo account · verification simulated", detail: "No ID was checked. Demo verification is simulated for the hackathon." },
  verified_live: { label: "Identity verified", detail: "Confirmed by Stripe Identity." },
};

/** Verification copy that never overstates a Stripe test-mode check. */
export const verificationCopy = (status: Verification, stripeTestMode = false) =>
  status === "verified_live" && stripeTestMode
    ? { label: "Stripe test mode · not a real ID check", detail: "Stripe Identity ran in test mode, so no real ID was checked." }
    : VERIFICATION[status];

export const REPORT_REASONS = [
  { value: "harassment", label: "Harassment or bullying" },
  { value: "unsafe", label: "Made me feel unsafe" },
  { value: "spam", label: "Spam or scam" },
  { value: "impersonation", label: "Fake profile or impersonation" },
  { value: "other", label: "Something else" },
];
