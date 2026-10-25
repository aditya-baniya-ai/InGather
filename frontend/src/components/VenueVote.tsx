import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Car, ExternalLink, Footprints, LocateFixed, MapPin, Navigation, RefreshCw, Sparkles, Star, Vote } from "lucide-react";
import { api, type Proposal, type VenueOption, type VenuePoll } from "../lib/api";
import { keys } from "../lib/hooks";
import { VENUE_CATEGORIES } from "../lib/vocab";
import {
  appleMapsUrl, decidedWinner, etas, fmtMinutes, googleMapsUrl, prefersAppleMaps, stillVoting, tally, venueCatClass,
  venuePhotoActivity, votingProgress, type TallyRow,
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

/** The venue's own photo when the search found one, else a stock photo of that kind of place. */
function VenuePhoto({ o, city }: { o: VenueOption; city: string }) {
  const fallback = coverSrc(venuePhotoActivity(o.category), city);
  const [src, setSrc] = useState(o.image_url || fallback);
  return (
    <span className="relative block aspect-[16/10] overflow-hidden bg-sunk sm:aspect-auto sm:h-full sm:min-h-44">
      <img src={src} alt={o.image_url && src === o.image_url ? `Photo of ${o.name}` : ""} loading="lazy" referrerPolicy="no-referrer"
        onError={() => setSrc(fallback)} className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.04]" />
      {src === fallback && <span className="absolute right-2 bottom-2 rounded-full bg-black/55 px-2 py-0.5 text-[11px] text-white">Stock photo</span>}
    </span>
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

function VenueCard({ o, n, poll, city, active, winner, busy, onSelect, onRate }: {
  o: TallyRow; n: number; poll: VenuePoll; city: string; active: boolean; winner: VenueOption | null; busy: boolean;
  onSelect: () => void; onRate: (score: number) => void;
}) {
  const won = winner?.id === o.id;
  const apple = prefersAppleMaps();
  const primary = apple ? appleMapsUrl(o, city) : googleMapsUrl(o, city);
  return (
    <li className={venueCatClass(o.category)}>
      {/* Travel times sit in their own row below the rating; on wider screens its space is reserved, so hovering never moves anything. */}
      <article onMouseEnter={onSelect} onFocus={onSelect} onClick={onSelect}
        className={cx("group lift card grid overflow-hidden border-2 text-left transition-colors sm:grid-cols-[180px_1fr]",
          active || won ? "border-[var(--cat)]" : "border-transparent", winner && !won && "opacity-60")}>
        <a href={primary} target="_blank" rel="noopener noreferrer" aria-label={`Directions to ${o.name} in ${apple ? "Apple" : "Google"} Maps`} className="relative block">
          <VenuePhoto o={o} city={city} />
          <span className="absolute top-2 left-2 grid size-7 place-items-center rounded-full ig-grad text-[13px] font-bold text-white shadow">{n}</span>
          <span className="cat-pill absolute top-2 right-2 rounded-full px-2.5 py-0.5 text-[12px] font-semibold shadow-sm">{catLabel(o.category)}</span>
        </a>
        <div className="flex min-w-0 flex-col gap-1.5 p-4">
          <a href={primary} target="_blank" rel="noopener noreferrer" className="text-[16px] leading-snug font-semibold underline-offset-4 hover:underline">{o.name}</a>
          {o.area && <span className="flex items-start gap-1 text-[13px] text-muted"><MapPin className="mt-0.5 size-3.5 shrink-0" aria-hidden />{o.area}</span>}
          {o.description && <p className="text-[13.5px] leading-relaxed">{o.description}</p>}
          {o.why && <p className="text-[13px] leading-relaxed text-muted">{o.why}</p>}
          <div className="mt-auto pt-2">
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-x-3 text-[12.5px]">
              <span className="font-medium">{o.my_score ? `Your rating: ${o.my_score}/10` : "Rate it 1–10"}</span>
              <span className="inline-flex items-center gap-1 text-muted">
                <Star className="size-3.5" aria-hidden /> {o.average !== null ? <><span className="num font-semibold text-ink">{o.average.toFixed(1)}</span> avg · {o.ratings}/{poll.voters.length}</> : "no ratings yet"}
                {o.leading && !winner && <span className="font-semibold" style={{ color: "var(--cat-ink)" }}> · leading</span>}
              </span>
            </div>
            <Rating o={o} disabled={!!winner || busy} onRate={onRate} />
          </div>
        </div>
        {/* Travel times + directions: on hover or focus, and always for the selected card (tap on phones). */}
        <div className={cx("relative border-t border-line p-4 sm:col-span-2", active ? "block" : "hidden sm:block")}>
          {!active && <p className="absolute inset-0 hidden place-items-center text-[12.5px] text-muted sm:grid sm:group-hover:invisible sm:group-focus-within:invisible">Hover to see everyone's travel time and directions.</p>}
          <div className={cx("flex flex-wrap items-start justify-between gap-3", !active && "sm:invisible sm:group-hover:visible sm:group-focus-within:visible")}>
            <div className="min-w-0 flex-1 basis-64"><Travel o={o} poll={poll} /></div>
            <div className="flex flex-wrap gap-2 text-[12.5px] font-medium sm:flex-col">
              <a href={appleMapsUrl(o, city)} target="_blank" rel="noopener noreferrer" className="press inline-flex min-h-9 items-center gap-1.5 rounded-full bg-surface px-3 ring-1 ring-line hover:bg-sunk"><Navigation className="size-3.5" aria-hidden /> Apple Maps</a>
              <a href={googleMapsUrl(o, city)} target="_blank" rel="noopener noreferrer" className="press inline-flex min-h-9 items-center gap-1.5 rounded-full bg-surface px-3 ring-1 ring-line hover:bg-sunk"><Navigation className="size-3.5" aria-hidden /> Google Maps</a>
            </div>
          </div>
        </div>
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
  const select = useCallback((id: string) => setSelected(id), []);

  if (!data) return null;
  const winner = decidedWinner(data);
  const waiting = stillVoting(data);
  const rows = tally(data);
  const showMap = rows.some((o) => o.latitude !== null) || data.people.length > 0;

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
          <p className="text-[15px]">Muse Spark searches the web for 3 real public places near the middle of everyone (using the locations shared above, or rough home areas), open at your meetup time. Then everyone rates each place from 1 to 10.</p>
          <Button className="mt-4" loading={busy === "start"} onClick={() => act("start", () => api.startVenuePoll(p.id))} icon={<Sparkles className="size-4" aria-hidden />}>
            {busy === "start" ? "Searching nearby…" : "Find places near everyone"}
          </Button>
          {busy === "start" && <p role="status" className="mt-2 text-[13px] text-muted">Live web search can take up to a minute.</p>}
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

      {showMap && (
        <div className="mt-4">
          <GroupMap people={data.people} options={rows} selected={selected} onSelect={select} />
          <p className="mt-1.5 text-[12px] text-muted">Numbered pins are the places; round photos are group members who shared their location. Tap a pin or hover a card to see travel times.</p>
        </div>
      )}

      {rows.length > 0 && (
        <ul className="mt-4 grid gap-4" aria-label="Places to rate">
          {rows.map((o, i) => (
            <VenueCard key={o.id} o={o} n={i + 1} poll={data} city={p.city} active={selected === o.id} winner={winner} busy={!!busy}
              onSelect={() => select(o.id)} onRate={(score) => act(o.id, () => api.rateVenue(p.id, o.id, score))} />
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <ul className="mt-3 grid gap-1.5 text-[12.5px] md:grid-cols-3" aria-label="Sources">
          {rows.map((o) => (
            <li key={o.id} className="min-w-0">
              {o.verified && o.source_url
                ? <a href={o.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-1 text-emerald-ink underline-offset-2 hover:underline"><BadgeCheck className="size-3.5 shrink-0" aria-hidden /><span className="truncate">Verified via search · {o.name}</span><ExternalLink className="size-3 shrink-0" aria-hidden /></a>
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
        </div>
      )}
      <InlineError error={error} />
    </Panel>
  );
}
