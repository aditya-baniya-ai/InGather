import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronsUpDown, LogOut, UserRound } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDemoAccounts } from "../lib/hooks";
import { Avatar, cx } from "./ui";

/** Profile menu with the demo quick-switcher (Alice -> Sofia -> Jordan for the demo video). */
export function AccountMenu({ placement = "up", compact }: { placement?: "up" | "down"; compact?: boolean }) {
  const { me, signIn, signOut } = useAuth();
  const demo = useDemoAccounts();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  if (!me) return null;

  const switchTo = async (email: string) => {
    setSwitching(email);
    try {
      signIn(await api.demoLogin(email));
      setOpen(false);
      navigate("/home");
    } finally {
      setSwitching(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu"
        className={cx("press flex min-h-11 items-center gap-3 rounded-2xl text-left hover:bg-raised", compact ? "p-1" : "w-full p-2")}>
        <Avatar name={me.display_name} src={me.avatar_url} size={compact ? 34 : 36} />
        {!compact && (
          <span className="hidden min-w-0 flex-1 lg:block">
            <span className="block truncate text-[14px] font-medium">{me.display_name}</span>
            <span className="block truncate text-[12.5px] text-muted">{me.is_demo ? "Demo account" : me.email}</span>
          </span>
        )}
        {!compact && <ChevronsUpDown className="hidden size-4 text-muted lg:block" aria-hidden />}
        <span className="sr-only">Account menu</span>
      </button>
      {open && (
        <div role="menu" className={cx("rise absolute z-50 w-72 rounded-2xl border border-line bg-surface p-2 shadow-[0_16px_40px_rgb(31_34_48/0.16)]",
          placement === "up" ? "bottom-full left-0 mb-2 origin-bottom-left" : "top-full right-0 mt-2 origin-top-right")}>
          {demo.data && demo.data.length > 0 && (
            <div className="pb-2">
              <p className="px-3 pt-2 pb-1 text-[12.5px] text-muted">Switch demo account · simulated verification</p>
              {demo.data.map((a) => (
                <button key={a.email} role="menuitem" onClick={() => switchTo(a.email)} disabled={!!switching}
                  className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-1.5 text-left text-[14px] hover:bg-raised disabled:opacity-60">
                  <Avatar name={a.display_name} src={a.avatar_url} size={28} />
                  <span className="flex-1 truncate">{a.display_name}</span>
                  {a.email === me.email && <Check className="size-4 text-emerald" aria-label="Current account" />}
                  {switching === a.email && <span className="text-[12px] text-muted">Switching…</span>}
                </button>
              ))}
            </div>
          )}
          <div className={cx(!!demo.data?.length && "border-t border-line pt-2")}>
            <button role="menuitem" onClick={() => { setOpen(false); navigate("/profile"); }} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-[14px] hover:bg-raised">
              <UserRound className="size-4 text-muted" aria-hidden /> Profile & privacy
            </button>
            <button role="menuitem" onClick={signOut} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-[14px] hover:bg-raised">
              <LogOut className="size-4 text-muted" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
