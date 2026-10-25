import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Bot, Home, Inbox, PlusSquare, ShieldCheck, UserRound } from "lucide-react";
import { useInvitations } from "../lib/hooks";
import { AccountMenu } from "./AccountMenu";
import { LogoMark, Wordmark } from "./Brand";
import { cx } from "./ui";

/** Each nav item gets its own soft palette tile; the active one fills with the brand gradient. */
const TILE: Record<string, string> = {
  "/home": "bg-orange-soft text-orange-ink",
  "/invitations": "bg-rose-soft text-rose-ink",
  "/create": "bg-amber-soft text-amber-ink",
  "/agent": "bg-violet-soft text-violet-ink",
  "/profile": "bg-blue-soft text-blue-ink",
};

const NAV = [
  { to: "/home", label: "Home", icon: Home },
  { to: "/invitations", label: "Invitations", icon: Inbox },
  { to: "/create", label: "Create", icon: PlusSquare },
  { to: "/agent", label: "Gather Agent", icon: Bot },
  { to: "/profile", label: "Profile", icon: UserRound },
];

export const DISCLAIMER = "Independent prototype exploring a potential Instagram-style experience. Not affiliated with or endorsed by Instagram or Meta.";

function useInviteCount() {
  const inv = useInvitations();
  return inv.data?.filter((i) => i.status === "invited").length ?? 0;
}

function Badge({ n }: { n: number }) {
  if (!n) return null;
  return <span className="num grid min-w-5 h-5 place-items-center rounded-full ig-grad px-1.5 text-[11.5px] font-semibold text-white" aria-label={`${n} new`}>{n}</span>;
}

export function AppShell({ children, aside, chatAside = false }: { children: ReactNode; aside?: ReactNode; chatAside?: boolean }) {
  const invites = useInviteCount();
  const { pathname } = useLocation();
  const activePath = pathname.startsWith("/plans/") ? "/agent" : pathname.startsWith("/proposals/") ? "/invitations" : pathname;
  const isCurrent = (to: string) => activePath === to;
  return (
    <div className="min-h-dvh md:flex">
      {/* Desktop / tablet rail */}
      <nav aria-label="Main" className="sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line/70 bg-surface/50 px-3 py-6 md:flex md:w-[76px] lg:w-[244px]">
        <Link to="/home" className="mb-8 flex min-h-11 items-center px-2" aria-label="ingather home">
          <span className="lg:hidden"><LogoMark size={30} /></span>
          <Wordmark className="hidden lg:inline-flex" />
        </Link>
        <ul className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={to} className={() => cx(
                "press group flex min-h-12 items-center gap-3 rounded-2xl px-2 text-[15px] hover:bg-surface/80",
                isCurrent(to) ? "bg-surface font-semibold text-ink shadow-[0_6px_20px_-12px_rgb(214_41_118/0.5)]" : "text-ink/85")}>
                {() => (<>
                  <span className={cx("relative grid size-9 place-items-center rounded-xl transition-colors duration-200", isCurrent(to) ? "ig-grad text-white" : TILE[to])}>
                    <Icon className="size-[20px]" strokeWidth={isCurrent(to) ? 2.25 : 1.75} aria-hidden />
                    {to === "/invitations" && invites > 0 && <span className="absolute -right-2 -top-2 lg:hidden"><Badge n={invites} /></span>}
                  </span>
                  <span className="hidden flex-1 lg:inline">{label}</span>
                  {to === "/invitations" && <span className="hidden lg:inline"><Badge n={invites} /></span>}
                  <span className="sr-only lg:hidden">{label}</span>
                </>)}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="mt-auto"><AccountMenu /></div>
      </nav>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line/70 bg-surface/90 backdrop-blur px-4 pt-[env(safe-area-inset-top)] md:hidden">
        <Link to="/home" aria-label="ingather home"><Wordmark /></Link>
        <div className="flex items-center gap-1">
          <NavLink to="/invitations" className="press relative grid size-11 place-items-center rounded-full hover:bg-raised" aria-label={`Invitations${invites ? `, ${invites} new` : ""}`}>
            <Inbox className="size-[22px]" strokeWidth={1.75} aria-hidden />
            {invites > 0 && <span className="absolute right-1 top-1"><Badge n={invites} /></span>}
          </NavLink>
          <AccountMenu placement="down" compact />
        </div>
      </header>

      <div className="flex min-w-0 flex-1 justify-center gap-8 px-4 md:px-8">
        <main id="main" className="w-full max-w-[680px] min-w-0 pt-5 pb-28 md:pt-10 md:pb-12">
          {children}
          <footer className="mt-16 text-[12.5px] leading-relaxed text-muted">{DISCLAIMER}</footer>
        </main>
        <aside aria-label="Context" className={cx("sticky top-0 hidden h-dvh shrink-0 overflow-y-auto py-10 xl:block", chatAside ? "w-[360px] 2xl:w-[400px]" : "w-[320px]")}>
          {aside ?? <SafetyTips />}
        </aside>
      </div>

      {/* Mobile bottom nav */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden">
        <ul className="grid grid-cols-5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={to} className={() => cx("press relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px]", isCurrent(to) ? "font-semibold text-ink" : "text-muted")}>
                {() => (<>
                  {isCurrent(to) && <span aria-hidden className="rise ig-grad absolute top-0 h-[3px] w-8 rounded-b-full" />}
                  <Icon className="size-6" strokeWidth={isCurrent(to) ? 2.25 : 1.6} aria-hidden />
                  <span>{label === "Gather Agent" ? "Agent" : label}</span>
                </>)}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}

export function SafetyTips() {
  return (
    <div className="rounded-[24px] bg-gradient-to-br from-emerald-soft to-surface p-5 shadow-[0_10px_30px_-16px_rgb(22_139_115/0.35)]">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold"><ShieldCheck className="size-4 text-emerald" aria-hidden /> Meeting someone new</h2>
      <ul className="mt-3 flex flex-col gap-2.5 text-[14px] leading-snug text-ink/90">
        <li>Meet in a public, populated place.</li>
        <li>Arrange your own transportation.</li>
        <li>Keep your home, hotel and phone number to yourself.</li>
        <li>Tell someone you trust where you'll be.</li>
        <li>Leave whenever you feel uncomfortable. You never owe anyone a reason.</li>
      </ul>
      <p className="mt-4 text-[13px] text-muted">Identity verification helps confirm identity. It cannot guarantee someone's behavior.</p>
    </div>
  );
}
