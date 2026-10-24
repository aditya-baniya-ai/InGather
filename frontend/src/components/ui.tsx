import { useEffect, useId, useRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { AlertCircle, Loader2, RotateCw, X } from "lucide-react";
import { errorMessage } from "../lib/api";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger" | "agent";
const variants: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-[#33374a] disabled:bg-sunk disabled:text-muted",
  secondary: "bg-surface text-ink border border-control hover:border-ink/40 hover:bg-raised",
  ghost: "text-ink hover:bg-raised",
  danger: "bg-surface text-danger border border-danger/30 hover:bg-danger-soft",
  agent: "bg-violet text-white hover:bg-violet-ink disabled:bg-sunk disabled:text-muted aria-busy:bg-violet aria-busy:text-white",
};

export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        "press inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap select-none disabled:cursor-not-allowed",
        size === "sm" && "min-h-9 px-3.5 text-[14px]",
        size === "md" && "min-h-11 px-5 text-[15px]",
        size === "lg" && "min-h-12 px-6 text-[16px]",
        variants[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Panel({ as: Tag = "section", className, children, ...rest }: { as?: "section" | "div" | "article" | "aside"; className?: string; children: ReactNode; "aria-labelledby"?: string }) {
  return <Tag {...rest} className={cx("rounded-[20px] bg-surface border border-line", className)}>{children}</Tag>;
}

export function Pill({ tone = "neutral", children, className }: { tone?: "neutral" | "rose" | "violet" | "emerald" | "amber" | "danger"; children: ReactNode; className?: string }) {
  const tones = {
    neutral: "bg-raised text-muted",
    rose: "bg-rose-soft text-rose-ink",
    violet: "bg-violet-soft text-violet-ink",
    emerald: "bg-emerald-soft text-emerald-ink",
    amber: "bg-amber-soft text-amber-ink",
    danger: "bg-danger-soft text-danger",
  };
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12.5px] font-medium leading-5", tones[tone], className)}>{children}</span>;
}

function FieldShell({ label, hint, id, children, optional }: { label: string; hint?: ReactNode; id: string; children: ReactNode; optional?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[14px] font-medium">
        {label}{optional && <span className="font-normal text-muted"> · optional</span>}
      </label>
      {children}
      {hint && <p id={`${id}-hint`} className="text-[13px] text-muted">{hint}</p>}
    </div>
  );
}
const controlCls = "w-full rounded-xl border border-line bg-surface px-3.5 min-h-11 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-[#7a7d89] hover:border-control focus:border-violet focus:shadow-[0_0_0_3px_var(--color-violet-soft)]";

export function TextField({ label, hint, optional, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode; optional?: boolean }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} id={id} optional={optional}>
      <input id={id} aria-describedby={hint ? `${id}-hint` : undefined} className={cx(controlCls, className)} {...rest} />
    </FieldShell>
  );
}

export function TextArea({ label, hint, optional, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: ReactNode; optional?: boolean }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} id={id} optional={optional}>
      <textarea id={id} aria-describedby={hint ? `${id}-hint` : undefined} className={cx(controlCls, "py-3 leading-relaxed resize-y", className)} {...rest} />
    </FieldShell>
  );
}

export function SelectField({ label, hint, options, className, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: ReactNode; options: { value: string; label: string }[] }) {
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
        selected ? "border-ink bg-ink text-white" : "border-line bg-surface text-ink hover:border-control", className)}>
      {children}
    </button>
  );
}

export function Switch({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; disabled?: boolean }) {
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
    <span className={cx("inline-block shrink-0 rounded-full", ring ? "story-ring p-[2px]" : "")} style={{ width: size, height: size }} aria-hidden>
      <span className={cx("block size-full rounded-full", ring && "bg-surface p-[2px]")}>{inner}</span>
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
    <div className="rounded-[20px] border border-dashed border-control px-5 py-8 text-center">
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
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 id={id} className="text-[17px] font-semibold">{children}</h2>
      {action}
    </div>
  );
}
