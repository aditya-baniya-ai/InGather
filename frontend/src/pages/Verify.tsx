import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ExternalLink, FlaskConical, Loader2, ScanFace } from "lucide-react";
import { AppShell } from "../components/AppShell";
import { VerificationCard } from "../components/VerificationCard";
import { Button, buttonCls, EmptyState, ErrorState, InlineError, LoadingBlock, Pill } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { keys, useAction, useVerification } from "../lib/hooks";
import { verificationCopy } from "../lib/vocab";

const POLL_MS = 2000;
const POLL_FOR_MS = 20_000;

/** Onboarding step after Join, also reachable from Profile and agent errors. */
export function Verify() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const returned = params.get("done") === "1"; // back from Stripe; the webhook may still be on its way
  const [waiting, setWaiting] = useState(returned);
  const [adult, setAdult] = useState(false);
  const ver = useVerification(waiting ? POLL_MS : false);
  const status = ver.data?.status;

  useEffect(() => {
    if (!waiting) return;
    const t = setTimeout(() => setWaiting(false), POLL_FOR_MS);
    return () => clearTimeout(t);
  }, [waiting]);
  useEffect(() => {
    if (status && status !== "unverified") {
      setWaiting(false);
      qc.invalidateQueries({ queryKey: ["me"] });
    }
  }, [status, qc]);

  const demo = useAction(() => api.demoVerify(), [keys.verification], (m) => qc.setQueryData(["me"], m));
  const stripe = useAction(() => api.stripeStart(), [], ({ url }) => window.location.assign(url));

  if (!me || ver.isPending) return <AppShell><LoadingBlock label="Loading verification" /></AppShell>;
  if (ver.isError) return <AppShell><ErrorState error={ver.error} onRetry={() => ver.refetch()} what="your verification status" /></AppShell>;
  const v = ver.data;
  const verified = v.status !== "unverified";
  // A demo or Stripe test-mode check is never presented as a genuine "verified".
  const heading = v.status === "unverified" ? "Verify your account"
    : v.status === "verified_demo" ? "Demo verification on — simulated, no ID checked"
      : v.stripe_test_mode ? verificationCopy("verified_live", true).label : "You're verified";
  const discovery = me.can_discover ? "Discovery is available for your plans."
    : verified && !v.is_adult ? "Discovery is for adults only, so it stays off for your account."
      : verified ? "Discovery is still off. Check \"Pause all discovery\" in Profile." : "Discovery stays off until we know you're a real adult.";

  return (
    <AppShell>
      <header className="mb-6">
        <h1 className="page-title">{heading}</h1>
        <p className="mt-2 max-w-[60ch] text-[15px] text-muted">
          {discovery} Verification confirms identity and age.
          It doesn't make anyone safe to meet, so meetups stay in public places and you can leave or report anytime.
        </p>
      </header>

      <div className="flex flex-col gap-5">
        <VerificationCard me={me} />

        {returned && !verified && (
          <p role="status" className="flex items-center gap-2 rounded-2xl bg-raised px-4 py-3 text-[14.5px]">
            {waiting ? <><Loader2 className="size-4 animate-spin text-muted" aria-hidden /> Waiting for Stripe to send your result…</>
              : <>Stripe hasn't sent a result yet. It can take a few minutes. <button onClick={() => setWaiting(true)} className="min-h-11 font-medium underline underline-offset-4">Check again</button></>}
          </p>
        )}

        {verified ? (
          <div><Link to="/home" className={buttonCls("primary", "lg")}>Continue <ArrowRight className="size-4" aria-hidden /></Link></div>
        ) : !v.demo_available && !v.stripe_available ? (
          <EmptyState title="Verification isn't available on this server.">Your account still works for private plans. Discovery stays off.</EmptyState>
        ) : (
          <>
            {v.demo_available && (
              <section aria-labelledby="demo-v" className="rounded-[20px] border-2 border-dashed border-amber-ink/30 bg-amber-soft p-5">
                <h2 id="demo-v" className="flex items-center gap-2 text-[16px] font-semibold text-amber-ink">
                  <FlaskConical className="size-4" aria-hidden /> Demo verification — simulated, no ID checked
                </h2>
                <p className="mt-1 text-[14px] text-amber-ink">For the hackathon demo only. Your account is marked as a demo-verified adult on your word alone.</p>
                <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-2xl bg-surface p-4">
                  <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} className="size-4 shrink-0 accent-[var(--color-emerald)]" />
                  <span className="font-medium">I confirm I'm 18 or older</span>
                </label>
                <Button className="mt-4" disabled={!adult} loading={demo.isPending} onClick={() => demo.mutate(undefined)}>Use demo verification</Button>
                <InlineError error={demo.error} />
              </section>
            )}
            {v.stripe_available && (
              <section aria-labelledby="stripe-v" className="rounded-[20px] border border-line bg-surface p-5">
                <h2 id="stripe-v" className="flex flex-wrap items-center gap-2 text-[16px] font-semibold">
                  <ScanFace className="size-4" aria-hidden /> Verify with Stripe Identity
                  {v.stripe_test_mode && <Pill tone="amber">Test mode — not a real ID check</Pill>}
                </h2>
                <p className="mt-1 text-[14px] text-muted">Stripe checks a photo ID on its own site. InGather only keeps the result and whether you're 18 or older.</p>
                <Button variant="secondary" className="mt-4" loading={stripe.isPending} onClick={() => stripe.mutate(undefined)}
                  icon={<ExternalLink className="size-4" aria-hidden />}>Continue to Stripe</Button>
                <InlineError error={stripe.error} />
              </section>
            )}
            <Link to="/home" className="self-start text-[14.5px] font-medium text-muted underline-offset-4 hover:text-ink hover:underline min-h-11 inline-flex items-center">Not now — use private plans only</Link>
          </>
        )}
      </div>
    </AppShell>
  );
}
