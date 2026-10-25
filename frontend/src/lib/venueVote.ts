import type { VenuePoll, VenueOption } from "./api";

/** Category -> existing activity hue (.cat-*), so venue cards share the app's colour language. */
const CAT_CLASS: Record<string, string> = {
  cafe: "cat-coffee", restaurant: "cat-travel", food_hall: "cat-travel", museum: "cat-study",
  park: "cat-other", library: "cat-conference", conference_venue: "cat-conference", public_venue: "cat-event",
};
export const venueCatClass = (category: string) => CAT_CLASS[category] ?? "cat-other";

export interface TallyRow extends VenueOption { share: number; leading: boolean; mine: boolean }

/** Options in agent rank order with vote share; `leading` follows the backend rule (most votes, ties -> best rank). */
export function tally(poll: VenuePoll): TallyRow[] {
  const total = poll.options.reduce((n, o) => n + o.votes, 0);
  const leader = total > 0 ? winnerOf(poll.options) : null;
  return [...poll.options].sort((a, b) => a.rank - b.rank).map((o) => ({
    ...o, share: total ? o.votes / total : 0, leading: o.id === leader?.id, mine: o.id === poll.my_vote,
  }));
}

export function winnerOf(options: VenueOption[]): VenueOption | null {
  if (!options.length) return null;
  return [...options].sort((a, b) => b.votes - a.votes || a.rank - b.rank)[0];
}

/** The decided winner, only once the server says the vote is over. */
export const decidedWinner = (poll: VenuePoll) =>
  poll.status === "decided" ? poll.options.find((o) => o.id === poll.winner_option_id) ?? null : null;

export const stillVoting = (poll: VenuePoll) => poll.voters.filter((v) => !v.voted).map((v) => v.display_name);

export function votingProgress(poll: VenuePoll): string {
  const done = poll.voters.filter((v) => v.voted).length;
  return `${done} of ${poll.voters.length} voted`;
}
