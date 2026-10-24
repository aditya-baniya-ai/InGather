import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "../components/AppShell";
import { VerificationCard } from "../components/VerificationCard";
import { Avatar, Button, Chip, ErrorState, InlineError, LoadingBlock, Panel, Pill, Switch, TextArea, TextField } from "../components/ui";
import { api, type MePatch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { keys, useAction, useBlocks, useVerification } from "../lib/hooks";
import { INTEREST_SUGGESTIONS, verificationCopy } from "../lib/vocab";

function Section({ title, description, children, id }: { title: string; description?: ReactNode; children: ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="grid gap-3 py-6 md:grid-cols-[200px_1fr] md:gap-6">
      <div>
        <h2 id={id} className="text-[16px] font-semibold">{title}</h2>
        {description && <p className="mt-1 text-[13.5px] text-muted">{description}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function ConnectorCard() {
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const create = useAction(() => api.createConnectorToken(), [], (r) => setToken(r.token));
  const revoke = useAction(() => api.revokeConnectorTokens(), [], () => setToken(null));
  const mcpUrl = `${location.origin}/mcp`;
  const copy = async (what: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(what); setTimeout(() => setCopied(null), 1600); } catch { /* user can select manually */ }
  };
  const Row = ({ label, value, k }: { label: string; value: string; k: string }) => (
    <div>
      <p className="mb-1.5 text-[13px] text-muted">{label}</p>
      <div className="flex">
        <code className="min-h-11 min-w-0 flex-1 truncate rounded-l-xl border border-r-0 border-line bg-raised px-3 py-2.5 font-mono text-[13px]">{value}</code>
        <button onClick={() => copy(k, value)} className="press inline-flex min-h-11 items-center gap-1.5 rounded-r-xl border border-line bg-surface px-3 text-[14px] hover:bg-raised">
          {copied === k ? <Check className="size-4 text-emerald" aria-hidden /> : <Copy className="size-4" aria-hidden />}{copied === k ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
  return (
    <Panel className="flex flex-col gap-4 p-5">
      <p className="text-[14.5px]">Let your own Muse agent check your plans and invitations as you. It can't approve invites, confirm meetups or see anyone else's data. Those stay human taps in this app.</p>
      <Row label="MCP server URL" value={mcpUrl} k="url" />
      {token && (
        <div className="rise flex flex-col gap-2">
          <Row label="Connector token. Shown once; store it somewhere safe." value={token} k="token" />
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => create.mutate(undefined)} loading={create.isPending} icon={<KeyRound className="size-4" aria-hidden />}>{token ? "Create another token" : "Connect your Muse agent"}</Button>
        <Button variant="danger" onClick={() => revoke.mutate(undefined)} loading={revoke.isPending}>Revoke all tokens</Button>
      </div>
      {revoke.isSuccess && !token && <p role="status" className="text-[14px] text-emerald-ink">All connector tokens revoked.</p>}
      <InlineError error={create.error ?? revoke.error} />
    </Panel>
  );
}

export function Profile() {
  const { me, signOut } = useAuth();
  const qc = useQueryClient();
  const blocks = useBlocks();
  const ver = useVerification();
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!me) return;
    setName(me.display_name); setBio(me.bio ?? ""); setInterests(me.interests);
  }, [me]);

  const update = useAction((patch: MePatch) => api.updateMe(patch), [], (m) => qc.setQueryData(["me"], m));
  const unblock = useAction((id: string) => api.unblock(id), [keys.blocks]);

  if (!me) return <AppShell><LoadingBlock /></AppShell>;

  const save = (e: FormEvent) => {
    e.preventDefault();
    update.mutate({ display_name: name.trim(), bio: bio.trim(), interests }, { onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); } });
  };
  const toggle = (t: string) => setInterests((xs) => (xs.includes(t) ? xs.filter((x) => x !== t) : [...xs, t]));

  return (
    <AppShell>
      <header className="flex items-center gap-4 pb-2">
        <Avatar name={me.display_name} src={me.avatar_url} size={72} ring />
        <div className="min-w-0">
          <h1 className="truncate text-[26px] font-semibold leading-tight">{me.display_name}</h1>
          <div className="mt-1 flex flex-wrap gap-2">
            {me.is_demo || me.verification === "verified_demo" ? <Pill tone="amber">Demo account · verification simulated — no ID checked</Pill>
              : me.verification === "verified_live" ? <Pill tone={ver.data?.stripe_test_mode ? "amber" : "emerald"}>{verificationCopy("verified_live", ver.data?.stripe_test_mode).label}</Pill>
                : <Pill>Not verified</Pill>}
          </div>
        </div>
      </header>

      <div className="divide-y divide-line">
        <Section id="s-profile" title="Profile" description="What accepted group members see. Never your email, plans or schedule.">
          <form onSubmit={save} className="flex flex-col gap-4">
            <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} />
            <TextArea label="Bio" optional rows={3} maxLength={300} value={bio} onChange={(e) => setBio(e.target.value)} />
            <div>
              <p className="mb-2 text-[14px] font-medium">Interests</p>
              <div className="flex flex-wrap gap-2">
                {[...new Set([...INTEREST_SUGGESTIONS, ...interests])].map((t) => <Chip key={t} selected={interests.includes(t)} onClick={() => toggle(t)}>{t}</Chip>)}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button type="submit" loading={update.isPending}>Save profile</Button>
              {saved && <span role="status" className="text-[14px] text-emerald-ink">Saved</span>}
            </div>
            <InlineError error={update.error} />
          </form>
        </Section>

        <Section id="s-verify" title="Verification" description="A gate for discovery, not a safety rating.">
          <VerificationCard me={me} cta />
        </Section>

        <Section id="s-privacy" title="Privacy" description="Changes save immediately.">
          <Panel className="px-5 py-2">
            <Switch checked={me.discovery_paused} onChange={(v) => update.mutate({ discovery_paused: v })} disabled={update.isPending}
              label="Pause all discovery" description="Your agent stops searching and you won't be suggested to anyone." />
            <div className="border-t border-line" />
            <Switch checked={me.group_only} onChange={(v) => update.mutate({ group_only: v })} disabled={update.isPending}
              label="Group meetups only" description="Never suggest 1:1 meetups with people you haven't met." />
          </Panel>
          <p className="mt-3 text-[13.5px] text-muted">How AI uses your data: only for plans where you turned on AI processing, the agent sends minimized details (activity, city, dates, broad interests, your goal text) to Muse Spark. Exact times, email and identity data are never sent. Cancelled plans stop all matching right away; information already shared with a group can't be taken back.</p>
        </Section>

        <Section id="s-blocks" title="Blocked accounts" description="Blocked people are never matched or invited with you, and aren't told.">
          {blocks.isPending ? <LoadingBlock rows={1} />
            : blocks.isError ? <ErrorState error={blocks.error} onRetry={() => blocks.refetch()} what="blocked accounts" />
              : blocks.data.length === 0 ? <p className="text-[14.5px] text-muted">You haven't blocked anyone.</p>
                : (
                  <ul className="flex flex-col gap-2">
                    {blocks.data.map((b) => (
                      <li key={b.user_id} className="flex items-center gap-3 rounded-2xl bg-surface p-2 pr-3 ring-1 ring-line">
                        <Avatar name={b.display_name} size={36} />
                        <span className="flex-1">{b.display_name}</span>
                        <Button variant="ghost" size="sm" onClick={() => unblock.mutate(b.user_id)} loading={unblock.isPending && unblock.variables === b.user_id}>Unblock</Button>
                      </li>
                    ))}
                  </ul>
                )}
        </Section>

        <Section id="s-muse" title="Connect your Muse agent" description="Model Context Protocol connector, scoped to you.">
          <ConnectorCard />
        </Section>

        <Section id="s-account" title="Account">
          <p className="mb-3 text-[14.5px] text-muted">Signed in as {me.email}</p>
          <Button variant="secondary" onClick={signOut}>Sign out</Button>
        </Section>
      </div>
    </AppShell>
  );
}
