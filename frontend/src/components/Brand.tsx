import { useId } from "react";
import { cx } from "./ui";

/** Three linked circles: separate people, one overlap. Our own mark, no borrowed glyph. */
export function LogoMark({ size = 28, className }: { size?: number; className?: string }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#D94693" />
          <stop offset="1" stopColor="#7C57C2" />
        </linearGradient>
      </defs>
      <g fill="none" stroke={`url(#${id})`} strokeWidth="2.6">
        <circle cx="12" cy="12.5" r="6.5" />
        <circle cx="20" cy="12.5" r="6.5" />
        <circle cx="16" cy="19.5" r="6.5" />
      </g>
    </svg>
  );
}

export function Wordmark({ className, mark = true }: { className?: string; mark?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2 font-semibold tracking-[-0.03em] text-ink", className)}>
      {mark && <LogoMark />}
      <span className="text-[24px] leading-none">ingather<span className="text-rose">.</span></span>
    </span>
  );
}

const PALETTES: Record<string, [string, string, string]> = {
  conference: ["#7C57C2", "#D94693", "#F6C7DF"],
  travel: ["#168B73", "#7C57C2", "#C9EDE3"],
  hackathon: ["#1F2230", "#7C57C2", "#D94693"],
  study: ["#3E5BA9", "#7C57C2", "#DCD4F3"],
  coffee: ["#9A4F3A", "#D94693", "#F5D9CC"],
  event: ["#D94693", "#F08A4B", "#FBE0EE"],
  other: ["#5F6270", "#7C57C2", "#E6E4EC"],
};

function hash(s: string) {
  let h = 2166136261;
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

/** Plan cover: the real (Muse Image) cover when present, else a generated field of linked circles. */
export function Cover({ seed, activity, src, className, label }: { seed: string; activity: string; src?: string | null; className?: string; label?: string }) {
  const gid = useId();
  if (src) return <img src={src} alt={label ?? ""} className={cx("object-cover", className)} />;
  const [a, b, c] = PALETTES[activity] ?? PALETTES.other;
  const h = hash(seed);
  const circles = [0, 1, 2].map((i) => ({
    cx: 80 + ((h >>> (i * 5)) % 240),
    cy: 40 + ((h >>> (i * 7 + 3)) % 140),
    r: 46 + ((h >>> (i * 3 + 1)) % 60),
  }));
  return (
    <svg viewBox="0 0 400 225" preserveAspectRatio="xMidYMid slice" className={className} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={a} />
          <stop offset="1" stopColor={b} />
        </linearGradient>
      </defs>
      <rect width="400" height="225" fill={`url(#${gid})`} />
      {circles.map((ci, i) => (
        <circle key={i} cx={ci.cx} cy={ci.cy} r={ci.r} fill={i === 2 ? c : "none"} fillOpacity={0.18} stroke="#fff" strokeOpacity={0.55} strokeWidth={2} />
      ))}
    </svg>
  );
}
