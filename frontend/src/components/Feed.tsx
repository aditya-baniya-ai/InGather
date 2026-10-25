import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BrainCircuit, Check, Clock, Send, Sparkles, UsersRound } from "lucide-react";
import { Cover } from "./Brand";
import { Avatar, Button, EmptyState, ErrorState, InlineError, LoadingBlock, Pill, SectionTitle, cx } from "./ui";
import { api, type FeedItem } from "../lib/api";
import { DAYS, SORTS, matchesDay, remember, remembered, type DayFilter, type FeedSort } from "../lib/feed";
import { keys, useFeed } from "../lib/hooks";
import { CATEGORIES } from "../lib/vocab";

/** "Tue, Oct 27" from a plain YYYY-MM-DD (the group's local date). */
export function dayLabel(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

const PART = { morning: "Morning", afternoon: "Afternoon", evening: "Evening" };

function People({ item }: { item: FeedItem }) {
  const everyone = [item.host, ...item.members];
  return (
    <div className="flex items-center gap-3">
      <div className="flex -space-x-2">
        {everyone.map((p, i) => <span key={i} className="rounded-full ring-2 ring-surface"><Avatar name={p.first_name} src={p.avatar_url} size={32} /></span>)}
        {Array.from({ length: item.spots_left }, (_, i) => (
          <span key={`open-${i}`} className="grid size-8 place-items-center rounded-full border-2 border-dashed border-ig-pink/40 bg-surface text-[11px] font-medium text-rose-ink ring-2 ring-surface" aria-hidden>+1</span>
        ))}
      </div>
      <p className="text-[13.5px] text-muted">
        {everyone.map((p) => p.first_name).join(", ")} · {item.spots_left > 0
          ? <span className="font-medium text-rose-ink">{item.spots_left} {item.spots_left === 1 ? "spot" : "spots"} left</span>
          : <span>{everyone.length} going</span>}
      </p>
    </div>
  );
}

function JoinForm({ item, onDone }: { item: FeedItem; onDone: () => void }) {
  const qc = useQueryClient();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"draft" | "send" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [drafted, setDrafted] = useState<"live" | "template" | null>(null);
  const draft = async () => {
    setBusy("draft"); setError(null);
    try { const d = await api.draftJoin(item.proposal_id); setMessage(d.message); setDrafted(d.mode); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  const send = async () => {
    setBusy("send"); setError(null);
    try {
      const updated = await api.askToJoin(item.proposal_id, message.trim() || null);
      qc.setQueriesData<FeedItem[]>({ queryKey: keys.feed }, (old) => old?.map((i) => (i.proposal_id === updated.proposal_id ? updated : i)));
      qc.invalidateQueries({ queryKey: keys.feed });  // the other sort order, and the request moves to the top
      onDone();
    } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return (
    <div className="rise mt-4 rounded-2xl bg-raised p-4">
      <label htmlFor={`msg-${item.proposal_id}`} className="text-[14px] font-medium">Say hi to {item.host.first_name} <span className="font-normal text-muted">(optional)</span></label>
      <textarea id={`msg-${item.proposal_id}`} rows={3} maxLength={400} value={message} onChange={(e) => setMessage(e.target.value)}
        placeholder={`Hi! ${item.title} sounds fun. Would love to join.`}
        className="mt-2 w-full resize-none rounded-2xl border border-line bg-surface px-4 py-3 text-[14.5px] leading-relaxed outline-none focus:border-violet" />
      {drafted && <p className="mt-1 text-[12.5px] text-muted">{drafted === "live" ? "Drafted by Muse Spark from your profile. Edit it however you like." : "A starting point. Edit it however you like."}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={send} loading={busy === "send"} icon={<Send className="size-4" aria-hidden />}>Send request</Button>
        <Button variant="secondary" size="sm" onClick={draft} loading={busy === "draft"} icon={<Sparkles className="size-4" aria-hidden />}>Write it with Muse</Button>
        <Button variant="ghost" size="sm" onClick={onDone}>Cancel</Button>
      </div>
      <p className="mt-2 text-[12.5px] text-muted">{item.host.first_name} sees your name, bio, interests and this note. The exact time and place are shared once you're in.</p>
      <InlineError error={error} />
    </div>
  );
}

export function FeedCard({ item }: { item: FeedItem }) {
  const qc = useQueryClient();
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const withdraw = async () => {
    setError(null);
    try { await api.withdrawJoin(item.proposal_id); qc.invalidateQueries({ queryKey: keys.feed }); } catch (e) { setError(e); }
  };
  const shared = new Set(item.shared_interests.map((i) => i.toLowerCase()));
  const category = CATEGORIES.find((c) => c.activity === item.activity_type)?.label ?? "Plans";
  return (
    <article className="post @container" aria-labelledby={`feed-${item.proposal_id}`}>
      <div className="post-inner @4xl:grid @4xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        {/* The whole photo, uncropped (3:2): on top in a narrow card, beside the text once the card is wide enough. */}
        <div className={cx("relative overflow-hidden bg-[var(--cat-soft)] @4xl:flex @4xl:items-center", `cat-${item.activity_type}`)}>
          {/* A soft, blurred copy fills the space above and below the photo when the text side is taller. */}
          <Cover activity={item.activity_type} city={item.city} src={item.cover_url} className="absolute inset-0 hidden size-full scale-125 opacity-70 blur-2xl @4xl:block" />
          <Cover activity={item.activity_type} city={item.city} src={item.cover_url} label={item.cover_url ? `Photo of ${item.title}` : undefined} className="relative block aspect-[3/2] w-full" />
          <span className="cat-pill absolute top-3 left-3 rounded-full px-2.5 py-1 text-[12px] font-semibold shadow-sm">{category}</span>
        </div>
        <div className="flex min-w-0 flex-col p-4 sm:p-5">
          <header className="flex items-center gap-3">
            <Avatar name={item.host.first_name} src={item.host.avatar_url} size={38} ring />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14px] font-semibold">{item.host.first_name}'s group</p>
              <p className="truncate text-[12.5px] text-muted">{item.city} · {dayLabel(item.day)} · {PART[item.part_of_day]}</p>
            </div>
            <Pill tone="emerald"><BrainCircuit className="size-3" aria-hidden /> {item.match}% fit</Pill>
          </header>
          <h3 id={`feed-${item.proposal_id}`} className="mt-4 text-[19px] leading-snug font-semibold tracking-[-0.015em]">{item.title}</h3>
          <p className="mt-1 text-[13.5px] text-muted">{item.venue_kind} in {item.city}{item.preview ? ` · ${item.preview}` : ""}</p>
          <hr className="grad-rule my-4" />
          <ul className="flex flex-wrap gap-1.5" aria-label="Group interests">
            {item.group_interests.map((i) => (
              <li key={i} className={cx("rounded-full px-2.5 py-1 text-[12.5px]", shared.has(i.toLowerCase()) ? "bg-violet-soft font-medium text-violet-ink ring-1 ring-violet/30" : "bg-raised text-muted")}>{i}</li>
            ))}
          </ul>
          <div className="mt-4"><People item={item} /></div>
          <p className="mt-3 flex items-start gap-1.5 text-[13.5px]"><BrainCircuit className="mt-0.5 size-3.5 shrink-0 text-violet" aria-hidden /> {item.reason}</p>
          <div className="mt-auto pt-4">
            {item.request_status === "accepted" ? (
              <div className="rounded-2xl bg-emerald-soft p-4">
                <p className="flex items-center gap-1.5 font-semibold text-emerald-ink"><Check className="size-4" aria-hidden /> You're in!</p>
                {item.welcome && <p className="mt-1 text-[14px]">{item.welcome}</p>}
                <Link to={`/proposals/${item.proposal_id}`} className="mt-2 inline-flex min-h-11 items-center gap-1.5 text-[14.5px] font-medium underline-offset-4 hover:underline">
                  Open the group <ArrowRight className="size-4" aria-hidden />
                </Link>
              </div>
            ) : item.request_status === "pending" ? (
              <div className="flex flex-wrap items-center gap-3">
                <Pill tone="amber"><Clock className="size-3" aria-hidden /> Request sent · waiting for {item.host.first_name}</Pill>
                <Button variant="ghost" size="sm" onClick={withdraw}>Withdraw</Button>
              </div>
            ) : joining ? (
              <JoinForm item={item} onDone={() => setJoining(false)} />
            ) : (
              <Button onClick={() => setJoining(true)} icon={<UsersRound className="size-4" aria-hidden />}>Ask to join</Button>
            )}
            <InlineError error={error} />
          </div>
        </div>
      </div>
    </article>
  );
}

function ChipGroup<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="no-scrollbar -mx-4 flex items-center gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
      <span className="w-12 shrink-0 text-[12px] font-semibold tracking-wide text-muted uppercase">{label}</span>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cx("press min-h-9 shrink-0 rounded-full px-3.5 text-[13.5px] transition-colors",
            value === o.value ? "ig-grad font-medium text-white shadow-[0_4px_14px_-6px_rgb(214_41_118/0.6)]" : "bg-raised text-ink hover:bg-sunk")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Home feed: open groups with room for one or two more, ranked for you by the InGather matcher. */
export function FeedSection({ activity = null }: { activity?: string | null }) {
  const [sort, setSort] = useState<FeedSort>(() => remembered("ingather.feedSort", ["match", "soonest"] as const, "match"));
  const [day, setDay] = useState<DayFilter>(() => remembered("ingather.feedDay", ["any", "today", "tomorrow", "weekend"] as const, "any"));
  const feed = useFeed(sort, activity);
  const kind = activity ? CATEGORIES.find((c) => c.activity === activity)?.label : null;
  const shown = (feed.data ?? []).filter((i) => i.request_status || matchesDay(i.day, day));
  return (
    <section aria-labelledby="feed-title">
      <SectionTitle id="feed-title">{kind ? `${kind} groups with room for you` : "Groups with room for you"}</SectionTitle>
      <p className="mb-5 flex items-center gap-1.5 text-[13.5px] text-muted">
        <BrainCircuit className="size-3.5 shrink-0" aria-hidden /> Ranked for you by the InGather matcher from your interests and plans. Hosts approve every request.
      </p>
      <div className="mb-6 flex flex-col gap-2.5 rounded-[20px] border border-line bg-surface/80 p-3.5 shadow-[0_8px_24px_-18px_rgb(150_47_191/0.45)] backdrop-blur">
        <ChipGroup label="Sort" value={sort} options={SORTS} onChange={(v) => { setSort(v); remember("ingather.feedSort", v); }} />
        <div className="h-px bg-line" />
        <ChipGroup label="When" value={day} options={DAYS} onChange={(v) => { setDay(v); remember("ingather.feedDay", v); }} />
      </div>
      {feed.isPending ? <LoadingBlock label="Finding groups for you" rows={2} />
        : feed.isError ? <ErrorState error={feed.error} onRetry={() => feed.refetch()} what="your feed" />
          : shown.length === 0 ? (
            <EmptyState title={`No open ${kind ? `${kind.toLowerCase()} ` : ""}groups ${day === "any" ? "for you right now" : DAYS.find((d) => d.value === day)?.label.toLowerCase()}.`}>
              {day === "any" ? "When people near your plans have a spot open, they'll show up here. Verified accounts only." : "Try another day, or check back later."}
            </EmptyState>
          ) : (
            <>
              <div className="mb-4 flex items-center gap-3">
                <p className="shrink-0 text-[13px] font-medium text-muted" aria-live="polite">{shown.length} {shown.length === 1 ? "group" : "groups"} · {sort === "match" ? "best match first" : "soonest first"}</p>
                <hr className="grad-rule flex-1" />
              </div>
              <div className="flex flex-col gap-7">{shown.map((i) => <FeedCard key={i.proposal_id} item={i} />)}</div>
            </>
          )}
    </section>
  );
}
