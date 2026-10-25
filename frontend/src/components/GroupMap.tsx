import { useEffect, useRef, type ReactNode } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { MapPerson, VenueOption } from "../lib/api";
import { cx } from "./ui";

const PIN = ["#d62976", "#962fbf", "#4f5bd5"]; // brand pinks/purples/blues for places 1, 2, 3
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function venueIcon(n: number): L.DivIcon {
  return L.divIcon({
    className: "venue-pin",
    iconSize: [34, 34],
    iconAnchor: [17, 34],
    html: `<span class="venue-pin-body" style="background:${PIN[(n - 1) % PIN.length]}"><b>${n}</b></span>`,
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

/** The group's meetup map: members who shared their location, and the venue options as numbered pins.
 *  OpenStreetMap tiles. Hovering a pin previews the place (like Google Maps), clicking selects it; the active pin grows.
 *  The map re-fits to all pins whenever its size changes, until someone pans or zooms it. */
export function GroupMap({ people, options, active, onSelect, onHover, className, children }: {
  people: MapPerson[]; options: VenueOption[]; active: string | null;
  onSelect: (id: string) => void; onHover: (id: string | null) => void; className?: string; children?: ReactNode;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);
  const pins = useRef(new Map<string, L.Marker>());
  const bounds = useRef<L.LatLngBounds | null>(null);
  const touched = useRef(false);  // the user panned or zoomed: stop re-fitting
  const fitting = useRef(false);
  const handlers = useRef({ onSelect, onHover });
  handlers.current = { onSelect, onHover };

  const fit = () => {
    const m = map.current, b = bounds.current;
    if (!m || !b || touched.current) return;
    fitting.current = true;
    m.fitBounds(b, { padding: [40, 40], maxZoom: 15, animate: false });
    fitting.current = false;
  };

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { scrollWheelZoom: false, attributionControl: true }).setView([30.27, -97.74], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    layer.current = L.layerGroup().addTo(m);
    m.on("dragstart zoomstart", () => { if (!fitting.current) touched.current = true; });
    map.current = m;
    const resize = new ResizeObserver(() => { m.invalidateSize({ animate: false }); fit(); });
    resize.observe(el.current);
    return () => { resize.disconnect(); m.remove(); map.current = null; };
  }, []);

  // Build markers only when the places or people change (not on hover), then fit them all in view.
  useEffect(() => {
    const g = layer.current;
    if (!g) return;
    g.clearLayers();
    pins.current.clear();
    const points: L.LatLngExpression[] = [];
    options.forEach((o, i) => {
      if (o.latitude === null || o.longitude === null) return;
      const at: L.LatLngExpression = [o.latitude, o.longitude];
      points.push(at);
      const marker = L.marker(at, { icon: venueIcon(i + 1), title: o.name, keyboard: true, riseOnHover: true })
        .on("click", () => handlers.current.onSelect(o.id))
        .on("mouseover", () => handlers.current.onHover(o.id))
        .on("mouseout", () => handlers.current.onHover(null))
        .addTo(g);
      pins.current.set(o.id, marker);
    });
    people.forEach((p) => {
      const at: L.LatLngExpression = [p.latitude, p.longitude];
      points.push(at);
      L.marker(at, { icon: personIcon(p), title: p.is_me ? `${p.display_name} (you)` : p.display_name, keyboard: false }).addTo(g);
    });
    bounds.current = points.length ? L.latLngBounds(points) : null;
    touched.current = false;
    fit();
  }, [people, options]);

  // Highlight the active pin in place (no re-render of markers, so hovering never flickers).
  useEffect(() => {
    pins.current.forEach((marker, id) => {
      marker.getElement()?.classList.toggle("is-active", id === active);
      marker.setZIndexOffset(id === active ? 1000 : 0);
    });
  }, [active, options]);

  return (
    <div className={cx("relative overflow-hidden rounded-2xl border border-line", className)}>
      <div ref={el} className="group-map size-full" role="region" aria-label="Map of the group and the suggested places" />
      {children}
    </div>
  );
}
