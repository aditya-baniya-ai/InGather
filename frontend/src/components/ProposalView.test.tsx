import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ProposalView } from "./ProposalView";
import { AuthProvider } from "../lib/auth";
import type { Member, Proposal } from "../lib/api";

const member = (over: Partial<Member>): Member => ({
  user_id: over.display_name ?? "x", display_name: "X", avatar_url: null, interests: [], is_initiator: false,
  status: "suggested", reason: null, confirmed: false, ...over,
});

const base: Proposal = {
  id: "p1", plan_id: "plan1", version: 2, status: "pending_owner", activity_title: "Conference evening food",
  initiator_name: "Alice", initiator_user_id: "u-alice", latest_run_id: null, explanation: "Everyone shares an evening window.", start_at: "2027-01-17T23:00:00Z",
  end_at: "2027-01-18T00:00:00Z", timezone: "America/New_York", city: "Philadelphia", venue_label: "Food hall near Center City",
  venue_category: "food_hall", venue_verified: false, icebreaker: null, viewer_role: "owner", group_size: 3, my_status: null, i_confirmed: false,
  members: [
    member({ display_name: "Alice", is_initiator: true, status: "accepted" }),
    member({ display_name: "Sofia", reason: "Shares coffee and city exploring." }),
    member({ display_name: "Maya", status: "passed", reason: "Shares food." }),
  ],
};

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter></QueryClientProvider>);
}

describe("ProposalView viewer stages", () => {
  it("owner sees reasons, venue and that nothing has been sent", () => {
    wrap(<ProposalView proposal={base} onRun={() => {}} />);
    expect(screen.getByText("Your agent has a proposal")).toBeInTheDocument();
    expect(screen.getByText("Shares coffee and city exploring.")).toBeInTheDocument();
    expect(screen.getByText("Food hall near Center City")).toBeInTheDocument();
    expect(screen.getByText("No invitation has been sent yet.")).toBeInTheDocument();
    expect(screen.getByText(/Passed privately \(never notified\): Maya/)).toBeInTheDocument();
  });

  it("invitee sees only the limited preview: no roster, reasons or venue", () => {
    const p: Proposal = { ...base, viewer_role: "invitee", status: "invites_pending", explanation: "", start_at: "2027-01-17",
      end_at: null, venue_label: null, venue_category: null, members: [], my_status: "invited" };
    wrap(<ProposalView proposal={p} onRun={() => {}} />);
    expect(screen.getByText("You've been invited to a small meetup")).toBeInTheDocument();
    expect(screen.getByText(/Philadelphia · Sun, Jan 17 · from Alice/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Accept/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Decline/ })).toBeInTheDocument();
    expect(screen.queryByText(/Food hall/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Why this suggestion/)).not.toBeInTheDocument();
    expect(screen.queryByText("Sofia")).not.toBeInTheDocument();
  });

  it("member before final sees the group but no venue; at awaiting_final sees SafeMeet", () => {
    const members = [member({ display_name: "Alice", is_initiator: true, status: "accepted" }), member({ display_name: "Sofia", status: "accepted" })];
    const pre: Proposal = { ...base, viewer_role: "member", status: "invites_pending", explanation: "", start_at: "2027-01-17",
      end_at: null, venue_label: null, venue_category: null, members, my_status: "accepted" };
    const { unmount } = wrap(<ProposalView proposal={pre} onRun={() => {}} />);
    expect(screen.getByText("Sofia")).toBeInTheDocument();
    expect(screen.queryByText("SafeMeet confirmation")).not.toBeInTheDocument();
    expect(screen.queryByText(/Why this suggestion/)).not.toBeInTheDocument();
    unmount();

    wrap(<ProposalView proposal={{ ...base, viewer_role: "member", status: "awaiting_final", explanation: "", members, my_status: "accepted" }} onRun={() => {}} />);
    expect(screen.getByText("SafeMeet confirmation")).toBeInTheDocument();
    expect(screen.getByText(/Confirmed by/)).toHaveTextContent("Confirmed by 0 of 2 people");
    expect(screen.getByRole("button", { name: /I confirm/ })).toBeInTheDocument();
    expect(screen.queryByText(/safe meetup/i)).not.toBeInTheDocument();
  });
});
