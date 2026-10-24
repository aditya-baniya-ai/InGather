import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { api, type TokenOut } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDemoAccounts } from "../lib/hooks";
import { Wordmark } from "../components/Brand";
import { DISCLAIMER } from "../components/AppShell";
import { Avatar, Button, InlineError, TextField } from "../components/ui";

function DemoAccounts({ onToken }: { onToken: (t: TokenOut) => void }) {
  const demo = useDemoAccounts();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (!demo.data?.length) return null; // only exists when the backend runs in DEMO_MODE
  const go = async (email: string) => {
    setBusy(email); setError(null);
    try { onToken(await api.demoLogin(email)); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return (
    <section aria-labelledby="demo-title" className="rounded-[24px] border-2 border-dashed border-amber-ink/30 bg-amber-soft p-5">
      <h2 id="demo-title" className="flex items-center gap-2 text-[15px] font-semibold text-amber-ink">
        <FlaskConical className="size-4" aria-hidden /> Demo accounts — simulated verification
      </h2>
      <p className="mt-1 text-[13.5px] text-amber-ink">Fictional people for the hackathon demo. No ID was checked for any of them.</p>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {demo.data.map((a) => (
          <li key={a.email}>
            <button onClick={() => go(a.email)} disabled={!!busy}
              className="press flex min-h-14 w-full items-center gap-3 rounded-2xl bg-surface px-3 py-2 text-left hover:bg-raised disabled:opacity-60">
              <Avatar name={a.display_name} src={a.avatar_url} size={36} />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{busy === a.email ? "Signing in…" : `Continue as ${a.display_name}`}</span>
                {a.bio && <span className="block truncate text-[12.5px] text-muted">{a.bio}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <InlineError error={error} />
    </section>
  );
}

export function Login() {
  const { signedIn, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"signin" | "join">(params.get("join") ? "join" : "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const from = (location.state as { from?: string } | null)?.from ?? "/home";

  if (signedIn) return <Navigate to={from} replace />;

  const done = (t: TokenOut) => { signIn(t); navigate(from, { replace: true }); };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { done(mode === "join" ? await api.register(email, password, name) : await api.login(email, password)); }
    catch (err) { setError(err); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-dvh bg-ground px-4 py-8 sm:py-12">
      <div className="mx-auto flex max-w-[520px] flex-col gap-6">
        <Link to="/" className="self-start" aria-label="ingather home"><Wordmark /></Link>
        <section aria-labelledby="auth-title" className="rounded-[24px] border border-line bg-surface p-6 sm:p-8">
          <h1 id="auth-title" className="font-display text-[36px] leading-none">{mode === "join" ? "Start privately" : "Welcome back"}</h1>
          <p className="mt-2 text-[15px] text-muted">
            {mode === "join" ? "New accounts start unverified. Discovery stays off until identity and adulthood are verified." : "Sign in to your plans and invitations."}
          </p>
          <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
            {mode === "join" && <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} autoComplete="nickname" />}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            <TextField label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "join" ? 8 : undefined}
              autoComplete={mode === "join" ? "new-password" : "current-password"} hint={mode === "join" ? "At least 8 characters." : undefined} />
            <InlineError error={error} />
            <Button type="submit" size="lg" loading={busy}>{mode === "join" ? "Create account" : "Sign in"}</Button>
          </form>
          <p className="mt-5 text-center text-[14px] text-muted">
            {mode === "join" ? "Already have an account? " : "New here? "}
            <button className="min-h-11 font-medium text-ink underline underline-offset-4" onClick={() => { setMode(mode === "join" ? "signin" : "join"); setError(null); }}>
              {mode === "join" ? "Sign in" : "Join"}
            </button>
          </p>
        </section>
        <DemoAccounts onToken={done} />
        <p className="text-[12.5px] text-muted">{DISCLAIMER}</p>
      </div>
    </div>
  );
}
