import { ExternalLink, MapPin } from "lucide-react";
import type { Proposal } from "../lib/api";

/** Only provider-sourced meetup coordinates are embedded; never a private event origin. */
export function VenueMap({ p, compact = false }: { p: Proposal; compact?: boolean }) {
  if (!p.venue_label) return null;
  const place = p.venue_details;
  const located = place && Number.isFinite(place.latitude) && Number.isFinite(place.longitude);
  const query = encodeURIComponent(`${p.venue_label}, ${p.city}`);
  const link = located ? `https://www.openstreetmap.org/?mlat=${place.latitude}&mlon=${place.longitude}#map=17/${place.latitude}/${place.longitude}` : `https://www.google.com/maps/search/?api=1&query=${query}`;
  const embed = located ? `https://www.openstreetmap.org/export/embed.html?bbox=${place.longitude - .006},${place.latitude - .004},${place.longitude + .006},${place.latitude + .004}&layer=mapnik&marker=${place.latitude},${place.longitude}` : undefined;
  return (
    <section aria-label="Meetup location map" className="overflow-hidden rounded-2xl border border-line bg-surface">
      {embed && <iframe title={`Map of ${p.venue_label}`} src={embed} loading="lazy" referrerPolicy="no-referrer" className={`w-full border-0 ${compact ? "h-36" : "h-56"}`} />}
      <div className="p-3">
        <div className="flex items-start gap-2">
          <MapPin className="mt-0.5 size-4 shrink-0 text-rose-ink" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold break-words">{located ? p.venue_label : "Meetup location"}</p>
            <p className="text-[12.5px] text-muted">{[place?.address, p.city].filter(Boolean).join(" · ")}</p>
          </div>
          <a href={link} target="_blank" rel="noopener noreferrer" aria-label={`Open ${p.venue_label} in maps`} className="press grid size-9 shrink-0 place-items-center rounded-full bg-rose-soft text-rose-ink"><ExternalLink className="size-4" aria-hidden /></a>
        </div>
        <p className="mt-2 text-[12px] text-muted">{located ? `OpenStreetMap · ${place.distance_m < 1000 ? `${place.distance_m} m` : `${(place.distance_m / 1000).toFixed(1)} km`} from the event, straight-line estimate. Check hours and access.` : "Exact location isn't mapped yet. The organizer can select a mapped place before final confirmation."}</p>
      </div>
    </section>
  );
}
