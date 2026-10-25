import { describe, expect, it } from "vitest";
import type { VenuePoll } from "./api";
import { decidedWinner, stillVoting, tally, venueCatClass, votingProgress, winnerOf } from "./venueVote";

const opt = (id: string, rank: number, votes: number) => ({
  id, rank, votes, name: `Spot ${id}`, area: null, category: "cafe", why: "", reservation_url: null, source_url: null, verified: false,
});
const poll = (over: Partial<VenuePoll> = {}): VenuePoll => ({
  status: "open", round: 1, rerolls_left: 1, source: "grounded", my_vote: null, winner_option_id: null, proposal_version: 3,
  options: [opt("c", 3, 0), opt("a", 1, 0), opt("b", 2, 0)],
  voters: [{ user_id: "1", display_name: "Alice", voted: false }, { user_id: "2", display_name: "Sofia", voted: false }, { user_id: "3", display_name: "Maya", voted: false }],
  ...over,
});

describe("venue vote tally", () => {
  it("orders by agent rank and has no leader before any vote", () => {
    const rows = tally(poll());
    expect(rows.map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(rows.some((r) => r.leading)).toBe(false);
  });

  it("computes shares, marks my vote and the leader", () => {
    const rows = tally(poll({ my_vote: "c", options: [opt("a", 1, 1), opt("b", 2, 0), opt("c", 3, 3)] }));
    expect(rows.find((r) => r.id === "c")).toMatchObject({ share: 0.75, leading: true, mine: true });
    expect(rows.find((r) => r.id === "a")?.share).toBe(0.25);
  });

  it("breaks ties toward the higher-ranked option, like the server", () => {
    expect(winnerOf([opt("c", 3, 1), opt("b", 2, 1), opt("a", 1, 0)])?.id).toBe("b");
  });

  it("reveals a winner only once decided", () => {
    const p = poll({ options: [opt("a", 1, 2), opt("b", 2, 1)], winner_option_id: "a" });
    expect(decidedWinner(p)).toBeNull();
    expect(decidedWinner({ ...p, status: "decided" })?.id).toBe("a");
  });

  it("lists who is still voting and progress", () => {
    const p = poll({ voters: [{ user_id: "1", display_name: "Alice", voted: true }, { user_id: "2", display_name: "Sofia", voted: false }] });
    expect(stillVoting(p)).toEqual(["Sofia"]);
    expect(votingProgress(p)).toBe("1 of 2 voted");
  });

  it("maps categories onto existing hues", () => {
    expect(venueCatClass("cafe")).toBe("cat-coffee");
    expect(venueCatClass("unknown")).toBe("cat-other");
  });
});
