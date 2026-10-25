import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { FeedCard, dayLabel } from "./Feed";
import type { FeedItem } from "../lib/api";

const item: FeedItem = {
  proposal_id: "g1", title: "Board game night", activity_type: "event", city: "Austin", day: "2026-10-27", part_of_day: "evening",
  venue_kind: "Café", preview: "Game developer in Austin, into board games.", host: { first_name: "Gabriela", avatar_url: null },
  members: [{ first_name: "Ethan", avatar_url: null }], group_size: 2, spots_left: 2, group_interests: ["board games", "coffee", "anime"],
  shared_interests: ["coffee"], match: 58, reason: "You share coffee", free_then: null, request_status: null, welcome: null,
};

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

describe("FeedCard", () => {
  it("shows the group without exact time or place, and opens the request form", () => {
    wrap(<FeedCard item={item} />);
    expect(screen.getByText("Gabriela's group")).toBeInTheDocument();
    expect(screen.getByText("58% fit")).toBeInTheDocument();
    expect(screen.getByText(/2 spots left/)).toBeInTheDocument();
    expect(screen.getByText(/Austin · Tue, Oct 27 · Evening/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Ask to join/ }));
    expect(screen.getByRole("button", { name: /Write it with Muse/ })).toBeInTheDocument();
    expect(screen.getByText(/exact time and place are shared once you're in/)).toBeInTheDocument();
  });
  it("shows a pending request and an accepted one with the welcome note", () => {
    const { unmount } = wrap(<FeedCard item={{ ...item, request_status: "pending" }} />);
    expect(screen.getByText(/Request sent · waiting for Gabriela/)).toBeInTheDocument();
    unmount();
    wrap(<FeedCard item={{ ...item, request_status: "accepted", welcome: "Welcome, Alice! You all love coffee." }} />);
    expect(screen.getByText("You're in!")).toBeInTheDocument();
    expect(screen.getByText("Welcome, Alice! You all love coffee.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open the group/ })).toHaveAttribute("href", "/proposals/g1");
  });
  it("formats the group's local day", () => {
    expect(dayLabel("2026-10-27")).toMatch(/Tue/);
  });
});
