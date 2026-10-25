import type React from "react";
import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type KeyboardEvent, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { AlertCircle, Eye, EyeOff, Loader2, RotateCw, X } from "lucide-react";
import { errorMessage } from "../lib/api";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// Disabled-but-idle buttons go flat grey; a busy (loading) button keeps its animated gradient.
const GRAD = "ig-grad btn-grad text-white [&:disabled:not([aria-busy])]:bg-none [&:disabled:not([aria-busy])]:bg-sunk [&:disabled:not([aria-busy])]:text-muted [&:disabled:not([aria-busy])]:shadow-none";
type Variant = "primary" | "secondary" | "ghost" | "danger" | "agent";
const variants: Record<Variant, string> = {
  primary: GRAD,
  secondary: "bg-surface text-ink border border-control hover:border-ink/40 hover:bg-raised",
  ghost: "text-ink hover:bg-raised",
  danger: "bg-surface text-danger border border-danger/30 hover:bg-danger-soft",
  agent: GRAD,
};

type Size = "sm" | "md" | "lg";
/** Button look, shared with links that act as buttons. */
export const buttonCls = (variant: Variant = "primary", size: Size = "md", className?: string) => cx(
  "press inline-flex items-center justify-center gap-2 rounded-full font-medium max-w-full whitespace-normal text-center py-2 select-none disabled:cursor-not-allowed",
  size === "sm" && "min-h-9 px-3.5 text-[14px]",
  size === "md" && "min-h-11 px-5 text-[15px]",
  size === "lg" && "min-h-12 px-6 text-[16px]",
  variants[variant],
  className,
);

export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }) {
  return (
    <button {...rest} disabled={disabled || loading} aria-busy={loading || undefined} className={buttonCls(variant, size, className)}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Panel({ as: Tag = "section", className, children, ...rest }: { as?: "section" | "div" | "article" | "aside"; className?: string; children: ReactNode; "aria-labelledby"?: string }) {
  return <Tag {...rest} className={cx("card", className)}>{children}</Tag>;
}

export function Pill({ tone = "neutral", children, className }: { tone?: "neutral" | "rose" | "violet" | "emerald" | "amber" | "danger" | "cat"; children: ReactNode; className?: string }) {
  const tones = {
    neutral: "bg-raised text-muted",
    rose: "bg-rose-soft text-rose-ink",
    violet: "bg-violet-soft text-violet-ink",
    emerald: "bg-emerald-soft text-emerald-ink",
    amber: "bg-amber-soft text-amber-ink",
    danger: "bg-danger-soft text-danger",
    cat: "cat-pill",
  };
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12.5px] font-medium leading-5", tones[tone], className)}>{children}</span>;
}

function FieldShell({ label, hint, error, id, children, optional }: { label: ReactNode; hint?: ReactNode; error?: ReactNode; id: string; children: ReactNode; optional?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[14px] font-medium">
        {label}{optional && <span className="font-normal text-muted"> · optional</span>}
      </label>
      {children}
      {error ? <p id={`${id}-hint`} role="alert" className="text-[13px] text-danger">{error}</p>
        : hint && <p id={`${id}-hint`} className="text-[13px] text-muted">{hint}</p>}
    </div>
  );
}
const controlCls = "w-full rounded-xl border border-line bg-surface px-3.5 min-h-11 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-muted/80 hover:border-control focus:border-violet focus:shadow-[0_0_0_3px_var(--color-violet-soft)] aria-invalid:border-danger";

type FieldProps = { label: ReactNode; hint?: ReactNode; optional?: boolean };

export function TextField({ label, hint, optional, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & FieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} id={id} optional={optional}>
      <input id={id} aria-describedby={hint ? `${id}-hint` : undefined} className={cx(controlCls, className)} {...rest} />
    </FieldShell>
  );
}

/** Password input with a show/hide toggle and an optional live error. */
export function PasswordField({ label, hint, error, className, ...rest }: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & FieldProps & { error?: ReactNode }) {
  const id = useId();
  const [shown, setShown] = useState(false);
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <div className="relative">
        <input id={id} type={shown ? "text" : "password"} aria-invalid={!!error || undefined} aria-describedby={hint || error ? `${id}-hint` : undefined}
          className={cx(controlCls, "pr-12", className)} {...rest} />
        <button type="button" onClick={() => setShown((v) => !v)} aria-pressed={shown} aria-label="Show password"
          className="press absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-xl text-muted hover:text-ink">
          {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        </button>
      </div>
    </FieldShell>
  );
}

export function TextArea({ label, hint, optional, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} id={id} optional={optional}>
      <textarea id={id} aria-describedby={hint ? `${id}-hint` : undefined} className={cx(controlCls, "py-3 leading-relaxed resize-y", className)} {...rest} />
    </FieldShell>
  );
}

export function SelectField({ label, hint, options, className, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & FieldProps & { options: { value: string; label: string }[] }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} id={id}>
      <select id={id} className={cx(controlCls, "appearance-none bg-[length:16px] bg-[right_12px_center] bg-no-repeat pr-9", className)}
        style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235f6270' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}
        {...rest}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </FieldShell>
  );
}

/** Toggle chip used for interests, feedback, categories. */
export function Chip({ selected, onClick, children, className }: { selected?: boolean; onClick?: () => void; children: ReactNode; className?: string }) {
  return (
    <button type="button" aria-pressed={selected} onClick={onClick}
      className={cx("press min-h-9 rounded-full border px-3.5 text-[14px]",
        selected ? "heart-pop ig-grad border-transparent text-white" : "border-line bg-surface text-ink hover:border-ig-pink/40 hover:bg-rose-soft/50", className)}>
      {children}
    </button>
  );
}

export function Switch({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; description?: string; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <label htmlFor={id} className="text-[15px] font-medium">{label}</label>
        {description && <p className="text-[13.5px] text-muted mt-0.5">{description}</p>}
      </div>
      <button id={id} type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
        className={cx("relative mt-0.5 h-7 w-12 shrink-0 rounded-full transition-colors duration-200 disabled:opacity-50",
          checked ? "bg-emerald" : "bg-control")}>
        <span className={cx("absolute top-1 left-1 size-5 rounded-full bg-white shadow-sm transition-transform duration-200 ease-[var(--ease-out)]", checked && "translate-x-5")} />
      </button>
    </div>
  );
}

export function Avatar({ name, src, size = 40, ring }: { name: string; src?: string | null; size?: number; ring?: boolean }) {
  // Stable pale tint per person (identity, not data).
  const hue = [...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  const inner = src
    ? <img src={src} alt="" className="size-full rounded-full object-cover" />
    : <span className="grid size-full place-items-center rounded-full font-semibold" style={{ background: `hsl(${hue} 60% 92%)`, color: `hsl(${hue} 45% 28%)`, fontSize: size * 0.4 }}>{name.trim().charAt(0).toUpperCase() || "?"}</span>;
  return (
    <span className={cx("inline-block shrink-0 rounded-full", ring ? "story-ring p-[2px]" : "bg-gradient-to-br from-ig-orange/40 to-ig-purple/40 p-px")} style={{ width: size, height: size }} aria-hidden>
      <span className="block size-full rounded-full bg-surface p-[2px]">{inner}</span>
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}

export function LoadingBlock({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className={cx("h-16", i === 0 && "h-24")} />)}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-[24px] border border-dashed border-ig-pink/30 bg-gradient-to-br from-orange-soft/60 via-surface to-blue-soft/60 px-5 py-8 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-sm text-[14px] text-muted">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry, what = "this" }: { error: unknown; onRetry?: () => void; what?: string }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl bg-danger-soft/60 px-4 py-3 text-[14px]">
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="flex-1">
        <p>Couldn't load {what}. {errorMessage(error)}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-1 inline-flex min-h-9 items-center gap-1.5 font-medium underline-offset-4 hover:underline">
            <RotateCw className="size-3.5" aria-hidden /> Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  if (!error) return null;
  return <p role="alert" className="text-[14px] text-danger">{errorMessage(error)}</p>;
}

/** Native <dialog> modal: focus trapping, Esc and inert background come from the platform. */
export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby={titleId}
      onClick={(e) => { if (e.target === ref.current) onClose(); }}
      className="dialog-pop m-auto w-[min(520px,calc(100vw-32px))] max-h-[calc(100dvh-48px)] rounded-[24px] bg-surface p-0 text-ink shadow-[0_24px_64px_rgb(31_34_48/0.22)]">
      <div className="flex items-start justify-between gap-4 px-6 pt-6">
        <h2 id={titleId} className="text-[20px] font-semibold leading-tight">{title}</h2>
        <button onClick={onClose} aria-label="Close" className="press -mr-2 -mt-2 grid size-11 place-items-center rounded-full hover:bg-raised"><X className="size-5" /></button>
      </div>
      <div className="px-6 pt-3 pb-6">{children}</div>
      {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>}
    </dialog>
  );
}

export function SectionTitle({ children, action, id }: { children: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 id={id} className="section-title">{children}</h2>
        <span aria-hidden className="accent-bar mt-1.5 block" />
      </div>
      {action}
    </div>
  );
}

/** Small violet marker for values an AI agent filled in (violet = AI). */
export function AiMark({ children = "Filled by Intake agent" }: { children?: ReactNode }) {
  return (
    <span className="rise ml-2 inline-flex items-center gap-1.5 align-middle text-[12px] font-normal text-violet-ink">
      <span className="size-1.5 rounded-full bg-violet" aria-hidden />{children}
    </span>
  );
}

/** Segmented control with tablist semantics; arrow keys move between tabs. */
export function Tabs<T extends string>({ value, onChange, options, label, idBase }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string; idBase: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);
  const idx = options.findIndex((o) => o.value === value);
  useEffect(() => {
    const measure = () => { const el = refs.current[idx]; if (el) setInd({ x: el.offsetLeft, w: el.offsetWidth }); };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [idx, options.length]);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const i = (options.findIndex((o) => o.value === value) + step + options.length) % options.length;
    onChange(options[i].value);
    refs.current[i]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className="relative inline-flex rounded-full bg-raised p-1">
      {ind && <span aria-hidden className="tab-ind ig-grad absolute left-0 top-1 bottom-1 rounded-full shadow-[0_4px_14px_-6px_rgb(214_41_118/0.6)]" style={{ width: ind.w, transform: `translateX(${ind.x}px)` }} />}
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`${idBase}-tab-${o.value}`} aria-selected={on}
            aria-controls={`${idBase}-panel`} tabIndex={on ? 0 : -1} onClick={() => onChange(o.value)}
            className={cx("press relative z-10 inline-flex min-h-10 items-center gap-2 rounded-full px-4 text-[14.5px] font-medium transition-colors duration-200",
              on ? "text-white" : "text-muted hover:text-ink")}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

const BURST_COLORS = ["#feda75", "#fa7e1e", "#d62976", "#962fbf", "#4f5bd5"];
/** One-shot gradient confetti for rare celebration moments (a meetup confirmed). */
export function Burst() {
  return (
    <span className="burst" aria-hidden>
      {Array.from({ length: 22 }, (_, i) => {
        const a = (i / 22) * Math.PI * 2, d = 70 + (i % 4) * 28;
        return <i key={i} style={{ "--c": BURST_COLORS[i % 5], "--x0": `${20 + (i % 6) * 6}%`, "--dx": `${Math.cos(a) * d}px`, "--dy": `${Math.sin(a) * d - 20}px`, "--r": `${i * 47}deg`, "--d": `${(i % 5) * 30}ms` } as React.CSSProperties} />;
      })}
    </span>
  );
}
