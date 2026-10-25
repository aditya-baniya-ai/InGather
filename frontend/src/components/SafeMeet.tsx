import { useQuery } from "@tanstack/react-query";
import { VenueMap } from "./VenueMap";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, Check, MapPin, MessageCircle, Share2 } from "lucide-react";
import { api, type Member, type Proposal } from "../lib/api";
import { useSetProposal } from "../lib/hooks";
import { formatDateTime, localToUtcIso, utcToLocal } from "../lib/time";
import { VENUE_CATEGORIES } from "../lib/vocab";
import { Avatar, Burst, Button, InlineError, Panel, Pill, SelectField, TextField } from "./ui";

export const participantsOf = (p: Proposal): Member[] => p.members.filter((m) => m.is_initiator || m.status === "accepted");

export function VenueTime({ p }: { p: Proposal }) {
  const cat = VENUE_CATEGORIES.find((c) => c.value === p.venue_category)?.label;
  return (
    <div className="flex flex-col gap-4"><dl className="grid gap-3 sm:grid-cols-2">
      <div className="flex gap-3 rounded-2xl bg-violet-soft p-4">
        <CalendarClock className="mt-0.5 size-5 shrink-0 text-violet-ink" aria-hidden />
        <div><dt className="text-[13px] text-muted">When</dt><dd className="font-medium">{formatDateTime(p.start_at, p.timezone)}</dd></div>
      </div>
      <div className="flex gap-3 rounded-2xl bg-orange-soft p-4">
        <MapPin className="mt-0.5 size-5 shrink-0 text-orange-ink" aria-hidden />
        <div>
          <dt className="text-[13px] text-muted">Where · public place</dt>
          <dd className="font-medium">{p.venue_label ?? "A public spot to be decided"}</dd>
          <dd className="text-[13px] text-muted">{[cat, p.city].filter(Boolean).join(" · ")}{!p.venue_verified && " · suggestion, not a booking"}</dd>
        </div>
      </div>
    </dl><VenueMap p={p} /></div>
  );
}

export function FinalizeForm({ p, onDone }: { p: Proposal; onDone?: () => void }) {
  const setProposal = useSetProposal();
  const toLocal = (iso: string | null) => (iso ? (({ date, time }) => `${date}T${time}`)(utcToLocal(iso, p.timezone)) : "");
  const [start, setStart] = useState(toLocal(p.start_at));
  const [end, setEnd] = useState(toLocal(p.end_at));
  const [venue, setVenue] = useState(p.venue_label ?? "");
  const [category, setCategory] = useState(p.venue_category ?? "cafe");
  const [placeId, setPlaceId] = useState("");
  const places = useQuery({ queryKey: ["nearby", p.plan_id], queryFn: () => api.nearbyPlaces(p.plan_id), enabled: false, retry: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const toUtc = (v: string) => (v ? localToUtcIso(v.slice(0, 10), v.slice(11, 16), p.timezone) : undefined);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      setProposal(await api.finalize(p.id, { start_at: toUtc(start), end_at: toUtc(end), venue_label: venue || undefined, venue_category: category, venue_place_id: placeId || undefined }));
      onDone?.();
    } catch (err) { setError(err); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="Starts" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required hint={`Local time in ${p.timezone.replace("_", " ")}`} />
        <TextField label="Ends" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <div className="rounded-2xl bg-violet-soft/50 p-4">
        <p className="font-semibold text-[14px]">Choose a place near your event</p>
        <p className="mt-1 text-[13px] text-muted">Uses the public event location saved on your plan. Search results are within 1.5 km, sorted by straight-line distance.</p>
        <Button type="button" variant="secondary" size="sm" className="mt-3" loading={places.isFetching} onClick={() => places.refetch()}>Find nearby cafés and restaurants</Button>
        {places.data && <><p role="status" className="mt-3 text-[13px] text-muted">{places.data.message}</p>
          {places.data.places.length > 0 && <div className="mt-3 flex flex-col gap-2">{places.data.places.map(place => <label key={place.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-surface p-3 text-[14px]">
            <input type="radio" name="venue-place" checked={placeId === place.id} onChange={() => { setPlaceId(place.id); setVenue(place.name); setCategory(place.category); }} className="mt-1 accent-[var(--color-violet)]" />
            <span><span className="font-semibold">{place.name}</span><span className="block text-[12.5px] text-muted">{place.address || p.city} · {place.distance_m} m away</span></span>
          </label>)}</div>}</>}
        <InlineError error={places.error} />
      </div>
      <TextField label="Public venue" value={venue} onChange={(e) => { setVenue(e.target.value); setPlaceId(""); }} maxLength={160} placeholder="A public café near the convention center" required />
      <SelectField label="Kind of place" value={category} onChange={(e) => { setCategory(e.target.value); setPlaceId(""); }} options={VENUE_CATEGORIES} />
      <p className="text-[13.5px] text-muted">Everyone, including you, confirms these exact details again. Changing them later asks for fresh confirmations.</p>
      <InlineError error={error} />
      <div><Button type="submit" loading={busy}>Send final details for confirmation</Button></div>
    </form>
  );
}

async function shareDetails(p: Proposal): Promise<string> {
  const text = `I'm meeting a small group I arranged on InGather.\n${p.activity_title}\nWhen: ${formatDateTime(p.start_at, p.timezone)}\nWhere: ${p.venue_label ?? "public place, TBD"}, ${p.city}`;
  if (navigator.share) {
    try { await navigator.share({ title: "My meetup details", text }); return "Shared."; }
    catch (e) { if ((e as DOMException).name === "AbortError") return ""; }
  }
  try { await navigator.clipboard.writeText(text); return "Copied. Paste it to someone you trust."; }
  catch { return "Couldn't copy automatically. Select and copy the details above."; }
}

/** Screen I: final details, per-person confirmation, safety reminders. Never claims safety. */
export function SafeMeet({ p }: { p: Proposal }) {
  const setProposal = useSetProposal();
  const people = participantsOf(p);
  const confirmedCount = people.filter((m) => m.confirmed).length;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [shareNote, setShareNote] = useState("");
  const confirmed = p.status === "confirmed";

  const confirm = async () => {
    setBusy(true); setError(null);
    try { setProposal(await api.confirm(p.id, p.version)); } catch (e) { setError(e); } finally { setBusy(false); }
  };

  return (
    <Panel className="p-5 sm:p-6" aria-labelledby="safemeet-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="safemeet-title" className="section-title">SafeMeet confirmation</h2>
        <Pill tone={confirmed ? "emerald" : "amber"}>
          {confirmed ? <Check className="size-3.5" aria-hidden /> : null}
          Confirmed by <span className="num">{confirmedCount}</span> of <span className="num">{people.length}</span> {people.length === 1 ? "person" : "people"}
        </Pill>
      </div>
      {confirmed && (
        <div className="rise relative mt-4">
          <Burst />
          <p className="page-title"><span className="ig-text">You're all in.</span></p>
          <p className="mt-2 max-w-prose text-[15px]">Meet in a public place, arrange your own transportation, and share details only with people you choose.</p>
        </div>
      )}
      <div className="mt-5"><VenueTime p={p} /></div>

      <ul className="mt-5 flex flex-col gap-2" aria-label="Who is confirmed">
        {people.map((m) => (
          <li key={m.user_id} className="flex items-center gap-3">
            <Avatar name={m.display_name} src={m.avatar_url} size={32} />
            <span className="flex-1 text-[15px]">{m.display_name}{m.is_initiator && <span className="text-muted"> · organizer</span>}</span>
            {m.confirmed ? <Pill tone="emerald"><Check className="size-3.5" aria-hidden /> Confirmed</Pill> : <Pill tone="neutral">Not yet</Pill>}
          </li>
        ))}
      </ul>

      {!confirmed && !p.i_confirmed && (
        <div className="mt-5">
          <Button onClick={confirm} loading={busy} icon={<Check className="size-4" aria-hidden />}>I confirm this time, place and group</Button>
          <InlineError error={error} />
        </div>
      )}
      {!confirmed && p.i_confirmed && <p className="mt-5 text-[14.5px] text-muted">You've confirmed. Waiting for everyone else; nothing is final until all confirm.</p>}

      <div className="mt-6 rounded-2xl bg-emerald-soft/60 p-4">
        <h3 className="text-[15px] font-semibold text-emerald-ink">Before you go</h3>
        <ul className="mt-2 grid gap-1.5 text-[14px]">
          <li>Meet only at the public place above.</li>
          <li>Arrange your own way there and back.</li>
          <li>Don't share your home, hotel or phone number.</li>
          <li>Tell someone you trust where you'll be.</li>
          <li>Leave if anything feels off.</li>
        </ul>
        <p className="mt-2 text-[13px] text-muted">InGather doesn't monitor meetups or provide emergency response.</p>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={async () => setShareNote(await shareDetails(p))} icon={<Share2 className="size-4" aria-hidden />}>Share with trusted contact</Button>
        {confirmed && (
          <Link to={`/proposals/${p.id}/room`} className="press inline-flex min-h-11 items-center gap-2 rounded-full ig-grad btn-grad px-5 font-medium text-white">
            <MessageCircle className="size-4" aria-hidden /> Open Gather Room
          </Link>
        )}
      </div>
      {shareNote && <p role="status" className="mt-2 text-[14px] text-muted">{shareNote}</p>}
    </Panel>
  );
}
