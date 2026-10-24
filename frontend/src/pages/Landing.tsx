import { Link } from "react-router-dom";
import { ArrowRight, Check, EyeOff, Lock, ShieldCheck, Sparkles, Wrench, type LucideIcon } from "lucide-react";
import { Cover, Wordmark } from "../components/Brand";
import { DISCLAIMER } from "../components/AppShell";
import { Avatar, Pill } from "../components/ui";

const FACTS: { icon: LucideIcon; text: string }[] = [
  { icon: EyeOff, text: "Plans are private by default. Nobody can browse your schedule, ever." },
  { icon: Check, text: "Two-sided consent: you approve each invite, they accept or decline freely, everyone confirms the final details." },
  { icon: ShieldCheck, text: "Identity verification helps confirm identity. It cannot guarantee someone's behavior, so SafeMeet keeps meetups public and leaving easy." },
];

const linkBtn = "press inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 font-medium";

/** A real piece of the product, drawn with the product's own components: the agent at work. */
function AgentPreview() {
  const rows = [
    { tool: "get_my_plan_context", text: "Read your private plan. It is never shown to anyone else." },
    { tool: "find_eligible_candidates", text: "4 opted-in plans in Philadelphia, Jan 17–19." },
    { tool: "check_group_availability", text: "A shared evening window exists for 3 people." },
  ];
  return (
    <div data-ui className="relative mx-auto w-full max-w-[440px]">
      <div className="overflow-hidden rounded-[28px] bg-surface shadow-[0_30px_80px_-30px_rgb(150_47_191/0.45)] ring-1 ring-ig-pink/10">
        <Cover activity="conference" city="Philadelphia" className="h-28 w-full" />
        <div className="p-5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[15px] font-semibold">Philly tech conference, after 5</p>
            <Pill tone="neutral"><Lock className="size-3" aria-hidden /> Private</Pill>
          </div>
          <ol className="mt-4 flex flex-col gap-3">
            {rows.map((r, i) => (
              <li key={r.tool} className="rise flex gap-3" style={{ animationDelay: `${200 + i * 140}ms` }}>
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-sunk"><Wrench className="size-3.5" aria-hidden /></span>
                <div className="min-w-0">
                  <code className="rounded-md bg-violet-ink px-1.5 py-0.5 font-mono text-[11.5px] text-white">{r.tool}</code>
                  <p className="mt-1 text-[13.5px] leading-snug">{r.text}</p>
                </div>
              </li>
            ))}
            <li className="rise flex gap-3" style={{ animationDelay: "640ms" }}>
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-violet-soft"><Sparkles className="size-3.5 text-violet" aria-hidden /></span>
              <p className="pt-1 text-[13.5px] leading-snug">I found a possible group with compatible plans. You choose who to invite.</p>
            </li>
          </ol>
          <div className="mt-5 flex items-center justify-between rounded-2xl bg-raised p-3">
            <div className="flex -space-x-2">
              {["Sofia", "Jordan", "Taylor"].map((n) => <span key={n} className="rounded-full ring-2 ring-raised"><Avatar name={n} size={34} /></span>)}
            </div>
            <span className="text-[13px] font-medium">Waiting for your approval</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Landing() {
  return (
    <div className="min-h-dvh bg-ground">
      <header className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-4 sm:px-8">
        <Wordmark />
        <nav className="flex items-center gap-1" aria-label="Account">
          <Link to="/login" className={`${linkBtn} text-ink hover:bg-raised`}>Sign in</Link>
          <Link to="/login?join=1" className={`${linkBtn} ig-grad btn-grad text-white`}>Join</Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-[1200px] items-center gap-12 px-4 pt-10 pb-20 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:pt-20">
          <div>
            <h1 className="font-display text-[52px] leading-[0.98] tracking-[-0.02em] sm:text-[76px] lg:text-[88px]">Go places.<br /><span className="ig-text">Find your people.</span></h1>
            <p className="mt-6 max-w-[34ch] text-[19px] leading-relaxed text-ink/90">
              Tell us what you want to do. Your Gather Agent finds a few compatible people, and you choose who to invite.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to="/login?join=1" className={`${linkBtn} ig-grad btn-grad min-h-12 px-6 text-[16px] text-white`}>Start privately <ArrowRight className="size-4" aria-hidden /></Link>
              <span className="text-[14px] text-muted">Less scrolling. More together.</span>
            </div>
          </div>
          <AgentPreview />
        </section>

        <section aria-labelledby="how" className="bg-[linear-gradient(120deg,#b01f60,#7a2299_55%,#3a46b8)] text-white">
          <div className="mx-auto max-w-[1200px] px-4 py-20 sm:px-8">
            <h2 id="how" className="max-w-[18ch] font-display text-[40px] leading-[1.02] sm:text-[52px]">AI handles the coordination. Humans choose the connection.</h2>
            <ol className="mt-12 grid gap-8 md:grid-cols-3">
              {[
                ["Tell your agent your plan", "A conference, a trip, a free evening. It stays private: no public post, no live location."],
                ["Review your people", "The agent calls real tools to find opted-in plans that overlap with yours, and tells you why. Pass on anyone, privately."],
                ["Approve a shared experience", "Only the people you approve are invited. Everyone confirms the same public place and time before it's on."],
              ].map(([t, d], i) => (
                <li key={t} className="border-t border-white/20 pt-5">
                  <p className="flex items-center gap-2 text-[20px] font-semibold">{t}{i < 2 && <ArrowRight className="hidden size-5 text-white/50 md:block" aria-hidden />}</p>
                  <p className="mt-2 text-[16px] leading-relaxed text-white/80">{d}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-labelledby="privacy" className="mx-auto grid max-w-[1200px] gap-10 px-4 py-20 sm:px-8 lg:grid-cols-2">
          <h2 id="privacy" className="font-display text-[40px] leading-[1.02] sm:text-[52px]">Your personal itinerary stays private until you choose what to share.</h2>
          <ul className="flex flex-col gap-5 text-[16px]">
            {FACTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex gap-4"><Icon className="mt-1 size-5 shrink-0 text-emerald" aria-hidden /><span>{text}</span></li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-8">
          <p className="text-[64px] font-semibold leading-none tracking-[-0.04em] sm:text-[120px]">ingather<span className="ig-text">.</span></p>
          <p className="mt-6 max-w-[70ch] text-[13px] text-muted">{DISCLAIMER} Hackathon demo: fictional profiles and simulated verification.</p>
        </div>
      </footer>
    </div>
  );
}
