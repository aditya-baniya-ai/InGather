import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Car, Clock, ExternalLink, Footprints, Globe, LocateFixed, MapPin, Navigation, Phone, RefreshCw, Sparkles, Star, Vote, X } from "lucide-react";
import { api, type Proposal, type VenueOption, type VenuePoll } from "../lib/api";
import { keys } from "../lib/hooks";
import { VENUE_CATEGORIES } from "../lib/vocab";
import {
  appleMapsUrl, decidedWinner, etas, fmtMinutes, googleMapsUrl, hostOf, hoursOn, photoOf, prefersAppleMaps, stillVoting, tally,
  venueCatClass, venuePhotoActivity, votingProgress, weekdayOf, type TallyRow,
} from "../lib/venueVote";
import { coverSrc } from "./Brand";
import { GroupMap } from "./GroupMap";
import { Avatar, Burst, Button, InlineError, Panel, Pill, cx } from "./ui";

/** Venue rating is possible once nobody is still `invited` and at least one person accepted. */
export const canVoteVenue = (p: Proposal) =>
  (p.status === "invites_pending" || p.status === "awaiting_final") &&
  !p.members.some((m) => m.status === "invited") &&
  p.members.some((m) => !m.is_initiator && m.status === "accepted");

const catLabel = (c: string) => VENUE_CATEGORIES.find((v) => v.value === c)?.label ?? c.replace("_", " ");

/** The place's photo (Google Maps, else one the web search found), else a stock photo of that kind of place. */
function VenuePhoto({ o, city, src: given, className }: { o: VenueOption; city: string; src?: string | null; className?: string }) {
  const fallback = coverSrc(venuePhotoActivity(o.category), city);
  const [src, setSrc] = useState(given ?? photoOf(o) ?? fallback);
  useEffect(() => setSrc(given ?? photoOf(o) ?? fallback), [given, o, fallback]);
  return (
    <span className={cx("relative block overflow-hidden bg-sunk", className)}>
      <img src={src} alt={src === fallback ? "" : `Photo of ${o.name}`} loading="lazy" referrerPolicy="no-referrer"
        onError={() => setSrc(fallback)} className="size-full object-cover" />
      {src === fallback && <span className="absolute right-2 bottom-2 rounded-full bg-black/55 px-2 py-0.5 text-[11px] text-white">Stock photo</span>}
    </span>
  );
}

/** Google-style rating: "4.6 ★★★★★ (812)". */
function Stars({ value, count }: { value: number; count: number | null }) {
  return (
    <span className="inline-flex items-center gap-1" aria-label={`Rated ${value.toFixed(1)} out of 5${count ? ` from ${count.toLocaleString()} reviews` : ""}`}>
      <span className="num font-medium text-ink">{value.toFixed(1)}</span>
      <span className="relative inline-block leading-none tracking-[1px] text-line" aria-hidden>★★★★★
        <span className="absolute inset-0 overflow-hidden text-[#f4b400]" style={{ width: `${(value / 5) * 100}%` }}>★★★★★</span>
      </span>
      {count !== null && <span className="text-muted">({count.toLocaleString()})</span>}
    </span>
  );
}

/** One line of Google facts: rating, kind of place, price, open now. */
function PlaceFacts({ o }: { o: VenueOption }) {
  const pl = o.place;
  if (!pl) return <span className="text-[13px] text-muted">{catLabel(o.category)}</span>;
  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[13px] text-muted">
      {pl.rating !== null && <Stars value={pl.rating} count={pl.rating_count} />}
      {pl.rating !== null && <span aria-hidden>·</span>}
      <span>{pl.type ?? catLabel(o.category)}</span>
      {pl.price && <><span aria-hidden>·</span><span>{pl.price}</span></>}
      {pl.open_now !== null && <><span aria-hidden>·</span><span className={cx("font-medium", pl.open_now ? "text-emerald-ink" : "text-danger")}>{pl.open_now ? "Open now" : "Closed now"}</span></>}
    </span>
  );
}

/** The Google-Maps-style place card: photos, rating, hours on the meetup day, address, phone, website, everyone's
 *  travel time and directions. Shown on the map when a place is hovered or selected, and inline on narrow screens. */
function PlaceDetails({ o, n, poll, city, day, meetupDay = true, onClose, className }: {
  o: VenueOption; n: number; poll: VenuePoll; city: string; day: string; meetupDay?: boolean; onClose?: () => void; className?: string;
}) {
  const pl = o.place;
  const photos = pl?.photos.length ? pl.photos : [{ url: photoOf(o) ?? "", author: null }];
  const [shown, setShown] = useState(0);
  useEffect(() => setShown(0), [o.id]);
  const dayHours = pl ? hoursOn(pl.hours, day) : null;
  const author = pl?.photos[shown]?.author;
  return (
    <section className={cx("overflow-hidden rounded-2xl bg-surface text-left", className)} aria-label={`${o.name} details`}>
      <div className="relative">
        <VenuePhoto o={o} city={city} src={photos[shown]?.url || null} className="aspect-[16/9] max-h-64 w-full" />
        <span className="absolute top-2 left-2 grid size-7 place-items-center rounded-full ig-grad text-[13px] font-bold text-white shadow">{n}</span>
        {onClose && <button type="button" onClick={onClose} aria-label="Close place details" className="press absolute top-2 right-2 grid size-8 place-items-center rounded-full bg-black/55 text-white"><X className="size-4" aria-hidden /></button>}
        {photos.length > 1 && (
          <div className="absolute inset-x-2 bottom-2 flex gap-1.5">
            {photos.map((ph, i) => (
              <button key={ph.url} type="button" onClick={(e) => { e.stopPropagation(); setShown(i); }} onMouseEnter={() => setShown(i)} aria-label={`Photo ${i + 1} of ${photos.length}`}
                className={cx("size-10 overflow-hidden rounded-lg ring-2 transition", i === shown ? "ring-white" : "ring-white/30 opacity-80 hover:opacity-100")}>
                <img src={ph.url} alt="" loading="lazy" referrerPolicy="no-referrer" className="size-full object-cover" />
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2 p-4">
        <h3 className="text-[17px] leading-snug font-semibold">{o.name}</h3>
        <PlaceFacts o={o} />
        {(pl?.summary || o.description) && <p className="text-[13.5px] leading-relaxed">{pl?.summary || o.description}</p>}
        <ul className="flex flex-col gap-1.5 border-t border-line pt-2.5 text-[13px]">
          {o.area && <li className="flex items-start gap-2"><MapPin className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />{o.area}</li>}
          {pl && pl.hours.length > 0 && (
            <li className="flex items-start gap-2"><Clock className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <details className="min-w-0 flex-1">
                <summary className="cursor-pointer list-none">{day}: <span className="font-medium">{dayHours ?? "hours not listed"}</span> <span className="text-muted">({meetupDay ? "meetup day" : "today"})</span></summary>
                <ul className="mt-1 text-muted">{pl.hours.map((h) => <li key={h}>{h}</li>)}</ul>
              </details>
            </li>
          )}
          {pl?.phone && <li className="flex items-center gap-2"><Phone className="size-4 shrink-0 text-muted" aria-hidden /><a href={`tel:${pl.phone}`} className="underline-offset-2 hover:underline">{pl.phone}</a></li>}
          {pl?.website && <li className="flex items-center gap-2"><Globe className="size-4 shrink-0 text-muted" aria-hidden /><a href={pl.website} target="_blank" rel="noopener noreferrer" className="truncate underline-offset-2 hover:underline">{hostOf(pl.website)}</a></li>}
        </ul>
        <div className="rounded-xl bg-raised p-3"><Travel o={o} poll={poll} /></div>
        <div className="flex flex-wrap gap-2 text-[13px] font-medium">
          <a href={appleMapsUrl(o, city)} target="_blank" rel="noopener noreferrer" className="press inline-flex min-h-10 items-center gap-1.5 rounded-full ig-grad px-3.5 text-white"><Navigation className="size-4" aria-hidden /> Apple Maps</a>
          <a href={googleMapsUrl(o, city)} target="_blank" rel="noopener noreferrer" className="press inline-flex min-h-10 items-center gap-1.5 rounded-full bg-surface px-3.5 ring-1 ring-line hover:bg-sunk"><Navigation className="size-4" aria-hidden /> Google Maps</a>
          {pl?.maps_url && <a href={pl.maps_url} target="_blank" rel="noopener noreferrer" className="press inline-flex min-h-10 items-center gap-1.5 rounded-full bg-surface px-3.5 ring-1 ring-line hover:bg-sunk"><ExternalLink className="size-4" aria-hidden /> Reviews</a>}
        </div>
        {pl && <p className="text-[11px] text-muted">Details and photos from Google Maps{author ? ` · Photo: ${author}` : ""}</p>}
      </div>
    </section>
  );
}

function Rating({ o, disabled, onRate }: { o: TallyRow; disabled: boolean; onRate: (n: number) => void }) {
  return (
    <div role="radiogroup" aria-label={`Your rating for ${o.name}, 1 to 10`} className="grid grid-cols-10 gap-1">
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
        const on = o.my_score !== null && n <= o.my_score;
        return (
          <button key={n} type="button" role="radio" aria-checked={o.my_score === n} aria-label={`${n} out of 10`} disabled={disabled}
            onClick={(e) => { e.stopPropagation(); onRate(n); }}
            className={cx("press num grid h-8 place-items-center rounded-lg text-[12.5px] font-semibold transition-colors disabled:cursor-default",
              on ? "ig-grad text-white" : "bg-raised text-muted hover:bg-sunk hover:text-ink")}>
            {n}
          </button>
        );
      })}
    </div>
  );
}

function Travel({ o, poll }: { o: VenueOption; poll: VenuePoll }) {
  const rows = etas(o, poll.people);
  if (o.latitude === null) return <p className="text-[12.5px] text-muted">No map pin for this place yet, so travel times aren't available.</p>;
  if (!rows.length) return <p className="text-[12.5px] text-muted">Share your location above to see how long it takes everyone to get here.</p>;
  return (
    <ul className="flex flex-col gap-1.5" aria-label={`Travel times to ${o.name}`}>
      {rows.map(({ person, km, walk, drive }) => (
        <li key={person.user_id} className="flex items-center gap-2 text-[13px]">
          <Avatar name={person.display_name} src={person.avatar_url} size={22} />
          <span className="min-w-0 flex-1 truncate">{person.is_me ? "You" : person.display_name.split(" ")[0]} <span className="text-muted">· {km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`}</span></span>
          <span className="inline-flex items-center gap-1 text-muted"><Footprints className="size-3.5" aria-hidden />{fmtMinutes(walk)}</span>
          <span className="inline-flex items-center gap-1 font-medium"><Car className="size-3.5" aria-hidden />{fmtMinutes(drive)}</span>
        </li>
      ))}
      <li className="text-[11.5px] text-muted">Estimates from distance; real routes may differ.</li>
    </ul>
  );
}

/** A result in the list, like Google Maps search results: hover previews it on the map, click keeps it open. */
function VenueCard({ o, n, poll, city, day, active, open, winner, busy, onHover, onSelect, onRate }: {
  o: TallyRow; n: number; poll: VenuePoll; city: string; day: string; active: boolean; open: boolean; winner: VenueOption | null; busy: boolean;
  onHover: (id: string | null) => void; onSelect: () => void; onRate: (score: number) => void;
}) {
  const won = winner?.id === o.id;
  return (
    <li className={venueCatClass(o.category)}>
      <article onMouseEnter={() => onHover(o.id)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(o.id)} onClick={onSelect}
        className={cx("lift card cursor-pointer overflow-hidden border-2 text-left transition-colors",
          active || won ? "border-[var(--cat)]" : "border-transparent", winner && !won && "opacity-60")}>
        <div className="flex gap-3 p-3">
          <div className="relative w-28 shrink-0 sm:w-32">
            <VenuePhoto o={o} city={city} className="aspect-square rounded-xl" />
            <span className="absolute top-1.5 left-1.5 grid size-6 place-items-center rounded-full ig-grad text-[12px] font-bold text-white shadow">{n}</span>
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <h3 className="text-[15.5px] leading-snug font-semibold">{o.name}</h3>
            <PlaceFacts o={o} />
            {o.area && <span className="truncate text-[12.5px] text-muted">{o.area}</span>}
            {o.why && <p className="line-clamp-2 text-[13px] leading-relaxed">{o.why}</p>}
          </div>
        </div>
        <div className="px-3 pb-3">
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-x-3 text-[12.5px]">
            <span className="font-medium">{o.my_score ? `Your rating: ${o.my_score}/10` : "Rate it 1–10"}</span>
            <span className="inline-flex items-center gap-1 text-muted">
              <Star className="size-3.5" aria-hidden /> {o.average !== null ? <><span className="num font-semibold text-ink">{o.average.toFixed(1)}</span> avg · {o.ratings}/{poll.voters.length}</> : "no ratings yet"}
              {o.leading && !winner && <span className="font-semibold" style={{ color: "var(--cat-ink)" }}> · leading</span>}
            </span>
          </div>
          <Rating o={o} disabled={!!winner || busy} onRate={onRate} />
        </div>
        {/* Narrow screens: the selected place opens right here (on wide screens it opens on the map). */}
        {open && <div className="border-t border-line @4xl:hidden" onClick={(e) => e.stopPropagation()}><PlaceDetails o={o} n={n} poll={poll} city={city} day={day} /></div>}
      </article>
    </li>
  );
}

function ShareLocation({ p, poll, onPoll }: { p: Proposal; poll: VenuePoll; onPoll: (v: VenuePoll) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const share = () => {
    if (!navigator.geolocation) return setError("This browser can't share a location.");
    setBusy(true); setError(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try { onPoll(await api.shareLocation(p.id, pos.coords.latitude, pos.coords.longitude)); }
        catch { setError("Couldn't save your location. Try again."); } finally { setBusy(false); }
      },
      (err) => { setBusy(false); setError(err.code === err.PERMISSION_DENIED ? "Location permission was blocked. Allow it in your browser to share." : "Couldn't get your location. Try again."); },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 },
    );
  };
  const stop = async () => { setBusy(true); try { onPoll(await api.stopSharingLocation(p.id)); } finally { setBusy(false); } };
  const others = poll.people.filter((x) => !x.is_me).length;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl bg-blue-soft/70 p-3.5">
      <LocateFixed className="size-5 shrink-0 text-blue-ink" aria-hidden />
      <p className="min-w-0 flex-1 text-[13.5px]">
        {poll.i_shared_location
          ? <>You're sharing your location with this group (to about 100 m).{others ? ` ${others} other ${others === 1 ? "person is" : "people are"} too.` : ""}</>
          : <>Share your location with this group so Muse finds places that are close to <b>everyone</b>. Great when you're new in town. Rounded to about 100 m, only this group sees it, and you can stop anytime.</>}
      </p>
      {poll.i_shared_location
        ? <Button variant="ghost" size="sm" loading={busy} onClick={stop}>Stop sharing</Button>
        : <Button variant="secondary" size="sm" loading={busy} onClick={share} icon={<LocateFixed className="size-4" aria-hidden />}>Share my location</Button>}
      {error && <p role="alert" className="w-full text-[13px] text-danger">{error}</p>}
    </div>
  );
}

/** Live progress while the venue agent works (Google Maps takes seconds; a live web search can take a minute). */
function Searching() {
  const [secs, setSecs] = useState(0);
  useEffect(() => { const t = window.setInterval(() => setSecs((x) => x + 1), 1000); return () => window.clearInterval(t); }, []);
  const step = secs < 4 ? "Finding real places near the middle of everyone…" : secs < 12 ? "Checking opening hours, ratings and distance for each person…" : "Muse is comparing the options and writing why each one fits…";
  return <p role="status" className="mt-2 text-[13px] text-muted">{step} <span className="num">{secs}s</span></p>;
}

/** The group rates 3 public places from the Muse venue agent, 1-10 each, on a shared map. Polls every 3 s. */
export function VenueVote({ p }: { p: Proposal }) {
  const qc = useQueryClient();
  const key = ["venue-poll", p.id];
  const poll = useQuery({ queryKey: key, queryFn: () => api.venuePoll(p.id), refetchInterval: (q) => (q.state.data?.status === "decided" ? false : 3000) });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);
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

  const setPoll = useCallback((v: VenuePoll) => qc.setQueryData(key, v), [qc, key.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (label: string, fn: () => Promise<VenuePoll>) => {
    setBusy(label); setError(null);
    try { setPoll(await fn()); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  // Hover previews a place (with a short grace period so you can move onto its card on the map); click keeps it open.
  const [hovered, setHovered] = useState<string | null>(null);
  const leave = useRef<number | undefined>(undefined);
  const hover = useCallback((id: string | null) => {
    window.clearTimeout(leave.current);
    if (id) setHovered(id);
    else leave.current = window.setTimeout(() => setHovered(null), 180);
  }, []);
  useEffect(() => () => window.clearTimeout(leave.current), []);
  const toggle = useCallback((id: string) => setSelected((cur) => (cur === id ? null : id)), []);

  if (!data) return null;
  const winner = decidedWinner(data);
  const waiting = stillVoting(data);
  const rows = tally(data);
  const showMap = rows.some((o) => o.latitude !== null) || data.people.length > 0;
  const shown = hovered ?? selected;
  const shownRow = rows.find((o) => o.id === shown) ?? null;
  const day = weekdayOf(p.start_at ?? new Date().toISOString(), p.timezone);  // invitees may not see the exact time yet: show today

  return (
    <Panel className="relative overflow-hidden p-5 sm:p-6" aria-labelledby="venue-vote-title">
      <div className="absolute inset-x-0 top-0 h-1 ig-grad-full" aria-hidden />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="venue-vote-title" className="section-title flex items-center gap-2"><Vote className="size-5 text-violet-ink" aria-hidden /> Pick the place together</h2>
        {data.status !== "not_started" && <Pill tone={winner ? "emerald" : "violet"}>{winner ? "Decided" : votingProgress(data)}</Pill>}
      </div>

      {!winner && <ShareLocation p={p} poll={data} onPoll={setPoll} />}

      {data.status === "not_started" && (
        <div className="mt-4">
          <p className="text-[15px]">Muse finds 3 real public places near the middle of everyone (using the locations shared above, or rough home areas), open at your meetup time, with photos, ratings and hours from the map. Then everyone rates each place from 1 to 10.</p>
          <Button className="mt-4" loading={busy === "start"} onClick={() => act("start", () => api.startVenuePoll(p.id))} icon={<Sparkles className="size-4" aria-hidden />}>
            {busy === "start" ? "Searching nearby…" : "Find places near everyone"}
          </Button>
          {busy === "start" && <Searching />}
        </div>
      )}

      {winner && (
        <div className="rise relative mt-4 rounded-2xl bg-emerald-soft/60 p-4">
          {reveal && <Burst />}
          <p className="text-[13px] font-medium text-emerald-ink">The group picked · {winner.average?.toFixed(1)} average</p>
          <p className="mt-1 text-[20px] font-semibold"><span className="ig-text">{winner.name}</span></p>
          <p className="mt-1 text-[14px] text-muted">Everyone now confirms the final details below. The earlier confirmations no longer count.</p>
          <a href={prefersAppleMaps() ? appleMapsUrl(winner, p.city) : googleMapsUrl(winner, p.city)} target="_blank" rel="noopener noreferrer"
            className="mt-2 inline-flex min-h-11 items-center gap-1.5 text-[14.5px] font-medium underline-offset-4 hover:underline"><Navigation className="size-4" aria-hidden /> Get directions</a>
        </div>
      )}

      {rows.length > 0 && (
        <div className="@container mt-4">
          <div className="flex flex-col gap-4 @4xl:grid @4xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] @4xl:items-start @4xl:gap-5">
            <ul className="order-2 flex flex-col gap-3 @4xl:order-1" aria-label="Places to rate">
              {rows.map((o, i) => (
                <VenueCard key={o.id} o={o} n={i + 1} poll={data} city={p.city} day={day} active={shown === o.id} open={selected === o.id}
                  winner={winner} busy={!!busy} onHover={hover} onSelect={() => toggle(o.id)}
                  onRate={(score) => act(o.id, () => api.rateVenue(p.id, o.id, score))} />
              ))}
            </ul>
            {showMap && (
              <div className="order-1 @4xl:sticky @4xl:top-4 @4xl:order-2">
                <GroupMap people={data.people} options={rows} active={shown} onSelect={toggle} onHover={hover}
                  className="h-72 sm:h-80 @4xl:h-[min(680px,calc(100dvh-7rem))]">
                  {shownRow && (
                    <div className="absolute top-3 bottom-3 left-3 z-[1000] hidden w-[min(330px,calc(100%-24px))] @4xl:block"
                      onMouseEnter={() => hover(shownRow.id)} onMouseLeave={() => hover(null)}>
                      <PlaceDetails o={shownRow} n={rows.indexOf(shownRow) + 1} poll={data} city={p.city} day={day} meetupDay={!!p.start_at}
                        onClose={selected ? () => setSelected(null) : undefined}
                        className="max-h-full overflow-y-auto shadow-[0_18px_50px_-18px_rgb(20_10_40/0.55)] ring-1 ring-line" />
                    </div>
                  )}
                </GroupMap>
                <p className="mt-1.5 text-[12px] text-muted">Hover a place or a numbered pin to see its photos, hours and everyone's travel time; click to keep it open. Round photos are members who shared their location.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <ul className="mt-3 grid gap-1.5 text-[12.5px] md:grid-cols-3" aria-label="Sources">
          {rows.map((o) => (
            <li key={o.id} className="min-w-0">
              {o.verified && o.source_url
                ? <a href={o.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-1 text-emerald-ink underline-offset-2 hover:underline"><BadgeCheck className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{o.place ? "Google Maps" : "Verified via search"} · {o.name}</span><ExternalLink className="size-3 shrink-0" aria-hidden /></a>
                : <span className="text-muted">Suggestion, not verified · {o.name}</span>}
            </li>
          ))}
        </ul>
      )}

      {data.status === "open" && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <p className="text-[13.5px] text-muted" role="status">{waiting.length ? `Still rating: ${waiting.join(", ")}.` : "Everyone has rated every place."} Rate all three; you can change a score until everyone's done.</p>
          {data.rerolls_left > 0 && (
            <Button variant="secondary" size="sm" loading={busy === "reroll"} disabled={!!busy} onClick={() => act("reroll", () => api.rerollVenues(p.id))} icon={<RefreshCw className="size-4" aria-hidden />}>
              Find more places ({data.rerolls_left} left)
            </Button>
          )}
          {busy === "reroll" && <div className="w-full"><Searching /></div>}
        </div>
      )}
      <InlineError error={error} />
    </Panel>
  );
}
