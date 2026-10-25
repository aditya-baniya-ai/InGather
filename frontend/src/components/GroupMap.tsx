import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { MapPerson, VenueOption } from "../lib/api";

const PIN = ["#d62976", "#962fbf", "#4f5bd5"]; // brand pinks/purples/blues for places 1, 2, 3
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function venueIcon(n: number, active: boolean): L.DivIcon {
  const size = active ? 40 : 32;
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size],
    html: `<span style="display:grid;place-items:center;width:${size}px;height:${size}px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
      background:${PIN[(n - 1) % PIN.length]};border:3px solid #fff;box-shadow:0 6px 16px -6px rgb(0 0 0 / .5)">
      <b style="transform:rotate(45deg);color:#fff;font:600 ${active ? 16 : 14}px var(--font-sans)">${n}</b></span>`,
  });
}

function personIcon(p: MapPerson): L.DivIcon {
  const inner = p.avatar_url
    ? `<img src="${esc(p.avatar_url)}" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover;background:#fff"/>`
    : `<span style="display:grid;place-items:center;width:100%;height:100%;border-radius:50%;background:#fff;color:#1f2230;font:600 14px var(--font-sans)">${esc(p.display_name.charAt(0))}</span>`;
  return L.divIcon({
    className: "",
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    html: `<span title="${esc(p.display_name)}" style="display:block;width:38px;height:38px;border-radius:50%;padding:2.5px;
      background:conic-gradient(#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5,#feda75);box-shadow:0 4px 12px -4px rgb(0 0 0 / .45)">${inner}</span>`,
  });
}

/** The group's meetup map: the shared locations of members who opted in, and the venue options (numbered pins).
 *  OpenStreetMap tiles; selecting a pin selects the option, and the selected option's pin grows. */
export function GroupMap({ people, options, selected, onSelect }: {
  people: MapPerson[]; options: VenueOption[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const fitted = useRef("");

  useEffect(() => {
    if (!el.current || map.current) return;
    map.current = L.map(el.current, { scrollWheelZoom: false, attributionControl: true }).setView([30.27, -97.74], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const points: L.LatLngExpression[] = [];
    options.forEach((o, i) => {
      if (o.latitude === null || o.longitude === null) return;
      const at: L.LatLngExpression = [o.latitude, o.longitude];
      points.push(at);
      L.marker(at, { icon: venueIcon(i + 1, o.id === selected), zIndexOffset: o.id === selected ? 1000 : 0, title: o.name, keyboard: true })
        .on("click", () => onSelect(o.id)).addTo(g);
    });
    people.forEach((p) => {
      const at: L.LatLngExpression = [p.latitude, p.longitude];
      points.push(at);
      L.marker(at, { icon: personIcon(p), title: p.is_me ? `${p.display_name} (you)` : p.display_name, keyboard: false }).addTo(g);
    });
    const key = points.map(String).join("|");
    if (points.length && key !== fitted.current) {  // re-fit only when the set of pins changes, not on every selection
      fitted.current = key;
      m.fitBounds(L.latLngBounds(points), { padding: [36, 36], maxZoom: 15 });
    }
  }, [people, options, selected, onSelect]);

  return <div ref={el} className="group-map h-72 w-full overflow-hidden rounded-2xl border border-line sm:h-80" role="region" aria-label="Map of the group and the suggested places" />;
}
