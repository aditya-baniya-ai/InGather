import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Lock, Plus } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { Cover } from "../components/Brand";
import { FeedSection } from "../components/Feed";
import { PlanCard } from "../components/PlanCard";
import { EmptyState, ErrorState, LoadingBlock, SectionTitle, cx } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useInvitations, usePlans } from "../lib/hooks";
import { CATEGORIES } from "../lib/vocab";

const IDEAS = [
  { activity: "conference", goal: "I'm in town for a conference and would love company for dinner after the sessions." },
  { activity: "travel", goal: "Visiting for a long weekend and looking for two or three people to explore museums with." },
  { activity: "study", goal: "Looking for a small study group at the library on weekday evenings." },
  { activity: "coffee", goal: "New to the city and up for a Saturday coffee with a few people into design." },
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Morning" : h < 18 ? "Afternoon" : "Evening";
}

/** Story-style category strip: horizontal scroll on phones, wraps on desktop. */
function Stories({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  return (
    <div role="group" aria-label="Filter plans by category" className="no-scrollbar -mx-4 flex gap-4 overflow-x-auto px-4 pb-1 md:mx-0 md:px-0">
      {CATEGORIES.map((c) => {
        const active = value === c.activity;
        return (
          <button key={c.label} onClick={() => onChange(active ? null : c.activity)} aria-pressed={active}
            className="press flex w-[68px] shrink-0 flex-col items-center gap-1.5 text-[12.5px]">
            <span className={cx("block size-[64px] rounded-full p-[2.5px] transition-transform duration-200 ease-[var(--ease-out)]", active ? "story-ring spin scale-105" : `cat-${c.activity ?? "other"} bg-[var(--cat)]/45`)}>
              <span className="block size-full overflow-hidden rounded-full border-[2.5px] border-surface">
                <Cover activity={c.activity ?? "other"} className="size-full" />
              </span>
            </span>
            <span className={cx(active ? "font-semibold text-ink" : "text-muted")}>{c.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Home() {
  const { me } = useAuth();
  const plans = usePlans();
  const invites = useInvitations();
  const [filter, setFilter] = useState<string | null>(null);
  const pendingInvites = invites.data?.filter((i) => i.status === "invited") ?? [];
  const mine = (plans.data ?? []).filter((p) => p.status !== "cancelled");
  const shown = filter ? mine.filter((p) => p.activity_type === filter) : mine;
  const ideas = IDEAS.filter((i) => !filter || i.activity === filter);
  const first = me?.display_name.split(" ")[0] ?? "";

  const fact = pendingInvites.length
    ? `${pendingInvites.length} ${pendingInvites.length === 1 ? "invitation is" : "invitations are"} waiting for your answer.`
    : mine.length ? `You have ${mine.length} private ${mine.length === 1 ? "plan" : "plans"}. Only you can see ${mine.length === 1 ? "it" : "them"}.`
      : "Tell your agent what you'd like to do. It stays private.";

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="page-title">{greeting()}, <span className="ig-text">{first}.</span></h1>
        <p className="mt-1 text-[16px] text-muted">{fact}</p>
      </header>

      <Stories value={filter} onChange={setFilter} />

      {pendingInvites.length > 0 && (
        <Link to="/invitations" className="press mt-6 flex min-h-14 items-center justify-between gap-3 rounded-[20px] bg-rose-soft px-5 py-3 hover:bg-[#f8dceb]">
          <span><span className="font-semibold text-rose-ink">You've been invited to a small meetup.</span>
            <span className="block text-[13.5px] text-ink/80">{pendingInvites[0].activity_title} · {pendingInvites[0].city}</span></span>
          <ArrowRight className="size-5 text-rose-ink" aria-hidden />
        </Link>
      )}

      {!filter && <FeedSection />}

      <section className="mt-8" aria-labelledby="plans-title">
        <SectionTitle id="plans-title" action={<Link to="/create" className="press inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-[14px] font-medium hover:bg-raised"><Plus className="size-4" aria-hidden /> New plan</Link>}>
          Your plans
        </SectionTitle>
        <p className="-mt-2 mb-4 flex items-center gap-1.5 text-[13.5px] text-muted"><Lock className="size-3.5" aria-hidden /> Your private itinerary is not public.</p>
        {plans.isPending ? <LoadingBlock label="Loading your plans" rows={2} />
          : plans.isError ? <ErrorState error={plans.error} onRetry={() => plans.refetch()} what="your plans" />
            : shown.length === 0 ? (
              <EmptyState title={filter ? "No plans in this category yet." : "No plans yet."}
                action={<Link to={filter ? `/create?activity=${filter}` : "/create"} className="press inline-flex min-h-11 items-center rounded-full ig-grad btn-grad px-5 font-medium text-white">Create a private plan</Link>}>
                Start with what you'd like to do. Your agent only searches when you ask.
              </EmptyState>
            ) : (
              <div className="flex flex-col gap-5">{shown.map((p, i) => <PlanCard key={p.id} plan={p} index={i} />)}</div>
            )}
      </section>

      {ideas.length > 0 && <section className="mt-10" aria-labelledby="ideas-title">
        <SectionTitle id="ideas-title">Start from an idea</SectionTitle>
        <ul className="divide-y divide-line overflow-hidden rounded-[20px] border border-line bg-surface">
          {ideas.map((idea) => (
            <li key={idea.goal}>
              <Link to={`/create?activity=${idea.activity}&goal=${encodeURIComponent(idea.goal)}`} className="flex min-h-14 items-center gap-4 px-4 py-3 hover:bg-raised">
                <span className="size-10 shrink-0 overflow-hidden rounded-xl"><Cover activity={idea.activity} className="size-full" /></span>
                <span className="flex-1 text-[14.5px]">{idea.goal}</span>
                <ArrowRight className="size-4 shrink-0 text-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </section>}
    </AppShell>
  );
}
