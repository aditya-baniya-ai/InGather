import { Link } from "react-router-dom";
import { ArrowRight, Check, FlaskConical, ShieldCheck, ShieldOff } from "lucide-react";
import type { Me } from "../lib/api";
import { useVerification } from "../lib/hooks";
import { verificationCopy } from "../lib/vocab";
import { buttonCls, Panel } from "./ui";

/** Screen C: verification status, honest about demo, Stripe test mode and live. */
export function VerificationCard({ me, cta }: { me: Me; cta?: boolean }) {
  const v = useVerification();
  const status = v.data?.status ?? me.verification;
  const copy = verificationCopy(status, v.data?.stripe_test_mode);
  const Icon = status === "verified_live" ? ShieldCheck : status === "verified_demo" ? FlaskConical : ShieldOff;
  const underage = status !== "unverified" && v.data?.is_adult === false;
  return (
    <Panel className="p-5">
      <ol className="flex flex-col gap-3 text-[14.5px]">
        <li className="flex items-center gap-3"><Check className="size-4 text-emerald" aria-hidden /> Account created</li>
        <li className="flex items-start gap-3">
          <Icon className={status === "unverified" ? "mt-0.5 size-4 text-muted" : status === "verified_live" && !v.data?.stripe_test_mode ? "mt-0.5 size-4 text-emerald" : "mt-0.5 size-4 text-amber-ink"} aria-hidden />
          <div>
            <p className="font-medium">Identity &amp; adulthood: {copy.label}</p>
            <p className="text-[13.5px] text-muted">{underage ? "Your verified date of birth is under 18. InGather discovery is for adults only." : copy.detail}</p>
          </div>
        </li>
        <li className="flex items-center gap-3">
          {me.can_discover ? <Check className="size-4 text-emerald" aria-hidden /> : <ShieldOff className="size-4 text-muted" aria-hidden />}
          Discovery {me.can_discover ? "available" : "unavailable"}
        </li>
      </ol>
      <p className="mt-4 rounded-2xl bg-raised p-3 text-[13.5px]">Verification confirms who someone is. It can't tell you whether they're safe to meet.</p>
      {cta && status === "unverified" && (
        <Link to="/verify" className={buttonCls("primary", "md", "mt-4")}>Verify your account <ArrowRight className="size-4" aria-hidden /></Link>
      )}
    </Panel>
  );
}
