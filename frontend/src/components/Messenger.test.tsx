import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MessengerProvider } from "./Messenger";
import { api, type Conversation } from "../lib/api";
const state = vi.hoisted(() => ({ signedIn: true }));
vi.mock('../lib/auth', () => ({ useAuth: () => ({ signedIn: state.signedIn, me: { id: 'alice', display_name: 'Alice' } }) }));
vi.mock('./DirectChat', () => ({ DirectChat: ({ person }: { person: { display_name: string } }) => <p>Private conversation with {person.display_name}</p> }));
vi.mock('./GatherChat', () => ({ GatherChat: () => <p>Group conversation</p> }));
vi.mock('../lib/hooks', () => ({ useAction: () => ({ mutate: () => {}, isPending: false, error: null }), useProposal: () => ({ isPending: false, isError: false, data: { id: 'group' } }) }));
const conversations: Conversation[] = [
  { id: 'group', kind: 'group', title: 'Conference coffee', people: [{ user_id: 'sofia', display_name: 'Sofia', avatar_url: null }], last_message: 'See you there', last_sender_name: 'Sofia', updated_at: '2027-01-17T20:00:00Z' },
  { id: 'sofia', kind: 'direct', title: 'Sofia', people: [{ user_id: 'sofia', display_name: 'Sofia', avatar_url: null }], last_message: null, last_sender_name: null, updated_at: '2027-01-17T20:00:00Z' },
];
function show() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MessengerProvider><p>Home page</p></MessengerProvider></QueryClientProvider>); }
beforeEach(() => { vi.restoreAllMocks(); state.signedIn = true; vi.spyOn(api, 'chats').mockResolvedValue(conversations); });

it('opens a searchable inbox and switches between group and individual conversations', async () => {
  show();
  fireEvent.click(screen.getByRole('button', { name: 'Messages' }));
  await screen.findByText('Conference coffee');
  fireEvent.click(screen.getByRole('button', { name: 'People' }));
  expect(screen.queryByText('Conference coffee')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: 'Search chats' }), { target: { value: 'nobody' } });
  expect(screen.getByText('No matching chats')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: 'Search chats' }), { target: { value: 'Sofia' } });
  fireEvent.click(screen.getByRole('button', { name: /Sofia Start a conversation/ }));
  expect(screen.getByText('Private conversation with Sofia')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to chats' }));
  fireEvent.click(screen.getByRole('button', { name: 'Groups' }));
  fireEvent.click(screen.getByRole('button', { name: /^Conference coffee/ }));
  expect(screen.getByText('Group conversation')).toBeInTheDocument();
});
it('closes with Escape and returns focus to the message icon', async () => {
  show();
  const trigger = screen.getByRole('button', { name: 'Messages' });
  fireEvent.click(trigger);
  await screen.findByRole('dialog');
  fireEvent.keyDown(document, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});
it('does not expose messaging or fetch conversations when signed out', () => {
  state.signedIn = false; show();
  expect(screen.queryByRole('button', { name: 'Messages' })).not.toBeInTheDocument();
  expect(api.chats).not.toHaveBeenCalled();
});
