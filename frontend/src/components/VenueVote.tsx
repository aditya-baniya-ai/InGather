import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Check, ExternalLink, MapPin, RefreshCw, Sparkles, Vote } from "lucide-react";
import { api, type Proposal, type VenuePoll } from "../lib/api";
import { keys } from "../lib/hooks";
import { VENUE_CATEGORIES } from "../lib/vocab";
import { decidedWinner, stillVoting, tally, venueCatClass, votingProgress } from "../lib/venueVote";
import { Burst, Button, InlineError, Panel, Pill, cx } from "./ui";

/** Venue vote is possible once nobody is still `invited` and at least one person accepted. */
export const canVoteVenue = (p: Proposal) =>
  (p.status === "invites_pending" || p.status === "awaiting_final") &&
  !p.members.some((m) => m.status === "invited") &&
  p.members.some((m) => !m.is_initiator && m.status === "accepted");

const catLabel = (c: string) => VENUE_CATEGORIES.find((v) => v.value === c)?.label ?? c.replace("_", " ");

/** Group picks one of 3 public places from the venue agent. Polls every 3 s for the live tally. */
export function VenueVote({ p }: { p: Proposal }) {
  const qc = useQueryClient();
  const key = ["venue-poll", p.id];
  const poll = useQuery({ queryKey: key, queryFn: () => api.venuePoll(p.id), refetchInterval: (q) => (q.state.data?.status === "decided" ? false : 3000) });
  const [busy, setBusy] = useState<string | null>(null);
  const [popped, setPopped] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const seenDecided = useRef<boolean | null>(null);
  const [reveal, setReveal] = useState(false);

  const data = poll.data;
  useEffect(() => {
    if (!data) return;
    const decided = data.status === "decided";
    if (seenDecided.current === false && decided) setReveal(true); // only celebrate a live transition
    seenDecided.current = decided;
    if (decided && data.proposal_version !== p.version) qc.invalidateQueries({ queryKey: keys.proposal(p.id) });
  }, [data, p.id, p.version, qc]);

  const act = async (label: string, fn: () => Promise<VenuePoll>) => {
    setBusy(label); setError(null);
    try { qc.setQueryData(key, await fn()); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const vote = (id: string) => { setPopped(id); act(id, () => api.voteVenue(p.id, id)); };

  if (!data) return null;
  const winner = decidedWinner(data);
  const waiting = stillVoting(data);

  return (
    <Panel className="relative overflow-hidden p-5 sm:p-6" aria-labelledby="venue-vote-title">
      <div className="absolute inset-x-0 top-0 h-1 ig-grad-full" aria-hidden />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="venue-vote-title" className="section-title flex items-center gap-2"><Vote className="size-5 text-violet-ink" aria-hidden /> Pick the place together</h2>
        {data.status !== "not_started" && <Pill tone={winner ? "emerald" : "violet"}>{winner ? "Decided" : votingProgress(data)}</Pill>}
      </div>

      {data.status === "not_started" && (
        <div className="mt-3">
          <p className="text-[15px]">The venue agent searches the web for 3 real public spots near the middle of your group, open at your meetup time. It only sees the city and a rounded midpoint, never anyone's location.</p>
          <Button className="mt-4" loading={busy === "start"} onClick={() => act("start", () => api.startVenuePoll(p.id))} icon={<Sparkles className="size-4" aria-hidden />}>
            {busy === "start" ? "Searching nearby…" : "Find 3 spots to vote on"}
          </Button>
          {busy === "start" && <p role="status" className="mt-2 text-[13px] text-muted">Live web search can take up to a minute.</p>}
        </div>
      )}

      {winner && (
        <div className="rise relative mt-4 rounded-2xl bg-emerald-soft/60 p-4">
          {reveal && <Burst />}
          <p className="text-[13px] font-medium text-emerald-ink">The group picked</p>
          <p className="mt-1 text-[20px] font-semibold"><span className="ig-text">{winner.name}</span></p>
          <p className="mt-1 text-[14px] text-muted">Everyone now confirms the final details below. The earlier confirmations no longer count.</p>
        </div>
      )}

      {data.options.length > 0 && (
        <ul className="mt-4 grid gap-3 md:grid-cols-3" aria-label="Venue options">
          {tally(data).map((o) => {
            const won = winner?.id === o.id;
            return (
              <li key={o.id} className={cx(venueCatClass(o.category), "flex")}>
                <button type="button" disabled={!!winner || !!busy} onClick={() => vote(o.id)} aria-pressed={o.mine}
                  onAnimationEnd={() => setPopped(null)}
                  className={cx("press lift card flex w-full flex-col gap-2 border-2 p-4 text-left disabled:cursor-default",
                    o.mine || won ? "border-[var(--cat)]" : "border-transparent", popped === o.id && "heart-pop", winner && !won && "opacity-60")}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="cat-pill rounded-full px-2.5 py-0.5 text-[12px] font-semibold">{catLabel(o.category)}</span>
                    {o.mine && <span className="inline-flex items-center gap-1 text-[12px] font-semibold" style={{ color: "var(--cat-ink)" }}><Check className="size-3.5" aria-hidden /> Your vote</span>}
                  </div>
                  <span className="text-[16px] font-semibold leading-snug">{o.name}</span>
                  {o.area && <span className="flex items-start gap-1 text-[13px] text-muted"><MapPin className="mt-0.5 size-3.5 shrink-0" aria-hidden />{o.area}</span>}
                  {o.why && <span className="text-[13.5px] leading-relaxed">{o.why}</span>}
                  <span className="mt-auto pt-1">
                    <span className="block h-2 overflow-hidden rounded-full bg-sunk" aria-hidden>
                      <span className="block h-full rounded-full transition-[width] duration-500" style={{ width: `${Math.round(o.share * 100)}%`, background: "var(--cat)" }} />
                    </span>
                    <span className="mt-1 block text-[12.5px] text-muted"><span className="num">{o.votes}</span> {o.votes === 1 ? "vote" : "votes"}{o.leading && !winner ? " · leading" : ""}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {data.options.length > 0 && (
        <ul className="mt-3 grid gap-1.5 text-[12.5px] md:grid-cols-3" aria-label="Sources">
          {tally(data).map((o) => (
            <li key={o.id} className="min-w-0">
              {o.verified && o.source_url
                ? <a href={o.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-1 text-emerald-ink underline-offset-2 hover:underline"><BadgeCheck className="size-3.5 shrink-0" aria-hidden /><span className="truncate">Verified via search · {o.name}</span><ExternalLink className="size-3 shrink-0" aria-hidden /></a>
                : <span className="text-muted">Suggestion — not verified · {o.name}</span>}
            </li>
          ))}
        </ul>
      )}

      {data.status === "open" && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13.5px] text-muted" role="status">{waiting.length ? `Still voting: ${waiting.join(", ")}` : "Everyone has voted."} Tap a card to vote or change your vote.</p>
          {data.rerolls_left > 0 && (
            <Button variant="ghost" size="sm" loading={busy === "reroll"} disabled={!!busy} onClick={() => act("reroll", () => api.rerollVenues(p.id))} icon={<RefreshCw className="size-4" aria-hidden />}>None of these work</Button>
          )}
        </div>
      )}
      <InlineError error={error} />
    </Panel>
  );
}
