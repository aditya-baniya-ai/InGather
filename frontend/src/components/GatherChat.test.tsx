import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GatherChat } from "./GatherChat";
import { api, type Proposal } from "../lib/api";

const state = vi.hoisted(() => ({ messages: [] as { id: string; sender_id: string | null; sender_name: string; body: string; created_at: string }[], enabled: false }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ me: { id: 'alice' } }) }));
vi.mock("../lib/hooks", async importOriginal => ({ ...await importOriginal<typeof import('../lib/hooks')>(), useMessages: (_id: string, enabled: boolean) => {
  state.enabled = enabled;
  return { data: state.messages, isPending: false, isError: false };
} }));
const p = {
  id: 'p1', plan_id: 'plan', status: 'confirmed', activity_title: 'Conference coffee', timezone: 'America/New_York',
  venue_label: null, members: [{ user_id: 'alice', display_name: 'Alice', is_initiator: true, status: 'accepted', avatar_url: '/avatars/alice.svg' },
    { user_id: 'sofia', display_name: 'Sofia', status: 'accepted', avatar_url: '/avatars/sofia.svg' }],
} as Proposal;
function show(proposal = p) {
  return render(<QueryClientProvider client={new QueryClient()}><GatherChat proposal={proposal} /></QueryClientProvider>);
}
beforeEach(() => { vi.restoreAllMocks(); state.messages = []; state.enabled = false; });

describe('GatherChat', () => {
  it('labels every message with its actual sender and avatar', () => {
    state.messages = [
      { id: '1', sender_id: 'alice', sender_name: 'Alice', body: 'Hello Sofia', created_at: '2027-01-17T23:00:00Z' },
      { id: '2', sender_id: 'sofia', sender_name: 'Sofia', body: 'Hello Alice', created_at: '2027-01-17T23:01:00Z' },
      { id: '3', sender_id: null, sender_name: 'Gather Agent', body: 'An icebreaker', created_at: '2027-01-17T23:02:00Z' },
    ];
    show();
    expect(within(screen.getByRole('article', { name: 'Message from Alice' })).getByText('Alice · You')).toBeInTheDocument();
    expect(within(screen.getByRole('article', { name: 'Message from Sofia' })).getByText('Sofia')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Message from Sofia' }).querySelector('img')).toHaveAttribute('src', '/avatars/sofia.svg');
    expect(screen.getByRole('article', { name: 'Message from Gather Agent' })).toBeInTheDocument();
  });
  it('never fetches messages or exposes a composer before confirmation', () => {
    show({ ...p, status: 'awaiting_final' });
    expect(state.enabled).toBe(false);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
  it('retains a failed message so it can be retried', async () => {
    vi.spyOn(api, 'sendMessage').mockRejectedValue(new Error('Network unavailable'));
    show();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'See you there' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByRole('textbox')).toHaveValue('See you there');
  });
});
